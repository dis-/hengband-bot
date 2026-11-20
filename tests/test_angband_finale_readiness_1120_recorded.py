"""The 99F/100F readiness, the supply plan, the weight and the small-floor option (angband_finale).

Owner 2026-11-20 (the 99F/100F directive and its answers, angband_finale's docstring): the 95F cap
lifts when a town board finds the Restore Mana target, Healing 30, *Healing* 15, Resistance 20,
Teleportation 40 carried and the equipment conditions met (speed, the resistances, telepathy, and
「呪力耐性も要求する」); the supplies are carried (kept, taken from Home, bought); the pack may be
over the weight limit while the speed after the slowdown is above +25; the option
always_small_floor is set before the descent.

Recorded: n1-b life-411's town arrival of 2026-11-20 03:32:34 (tests/fixtures/
n1b-411-home-closed-pending-1120): Lv50 Magic-Eater, Angband recall depth 95, speed 135, carrying
9 Healing, 9 Resistance, 15 Teleportation, no *Healing* and no Restore Mana (one at Home; target 25),
weight 2136 over its limit 1950, telepathy and resist curse worn.  Its Black Market page is row 80.
The dungeon boards are n1-b's recorded Angband 99F arrival (tests/fixtures/n1b-411-angband-cap-1119).

DECLARED CONSTRUCTED:
* ``stocked``: the recorded town board with the carried stacks set to the finale's counts (the
  recorded Healing, Resistance and Teleportation stacks raised, a *Healing* and a Restore Mana
  stack added by copying the Healing stack's row);
* ``without_curse``: ``stocked`` without the resist_curse ability;
* ``dungeon``: the recorded 99F board at the level asked;
* the Black Market ware: the page's first ware changed to *Healing*;
* the speed of the weight test (140 unslowed, less the slowdown of the weight asked) and its pack
  weights (one stack's weight changed); the Teleportation ware (the Black Market's first, changed).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_cap, angband_finale, consumable_policy
from hengbot.model import (
    DUNGEON_ANGBAND, STORE_BLACK, AbilitySources, SV_POTION_HEALING, SV_POTION_RESISTANCE, SV_POTION_RESTORE_MANA,
    SV_POTION_STAR_HEALING, SV_SCROLL_TELEPORT, TVAL_POTION, TVAL_SCROLL, parse_snapshot,
)
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-home-closed-pending-1120"
FLOOR_FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-angband-cap-1119"
BLACK_MARKET_ROW = 80
COUNTS = {(TVAL_POTION, SV_POTION_HEALING): 30, (TVAL_POTION, SV_POTION_STAR_HEALING): 15,
          (TVAL_POTION, SV_POTION_RESISTANCE): 20, (TVAL_SCROLL, SV_SCROLL_TELEPORT): 40,
          (TVAL_POTION, SV_POTION_RESTORE_MANA): 25}


class AngbandFinaleReadinessRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.arrival, _, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.town = steps[0][1]()
        cls.black_market = steps[BLACK_MARKET_ROW][1]()
        cls.raw = json.loads(lzma.decompress((FLOOR_FIXTURE / "angband-99f-board.json.xz").read_bytes()))

    @classmethod
    def tearDownClass(cls):
        cls.arrival._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def setUp(self):
        self.policy = copy.deepcopy(self.arrival)

    def stocked(self, board=None):
        """DECLARED CONSTRUCTED (the module docstring)."""
        board = board or self.town
        healing = next(item for item in board.inventory
                       if (item.tval, item.sval) == (TVAL_POTION, SV_POTION_HEALING))
        pack = [replace(item, count=COUNTS[(item.tval, item.sval)])
                if (item.tval, item.sval) in COUNTS else item for item in board.inventory]
        pack.append(replace(healing, slot="x", sval=SV_POTION_STAR_HEALING, count=15, name="*体力回復*の薬"))
        pack.append(replace(healing, slot="y", sval=SV_POTION_RESTORE_MANA, count=25, name="魔力復活の薬"))
        return replace(board, inventory=pack)

    def dungeon(self, level):
        raw = copy.deepcopy(self.raw)
        raw["floor"] = {**raw["floor"], "level": level}
        return parse_snapshot(raw, self.policy._monrace_knowledge)

    # -- (a) the readiness gate and the cap's lift --------------------------------------

    def test_a_recorded_board_is_short_and_keeps_the_cap(self):
        policy, board = self.policy, self.town
        rows = angband_finale.readiness(policy, board)
        self.assertEqual({name: (row.get("measured"), row.get("required"), row["ready"])
                          for name, row in rows.items() if "measured" in row},
                         {"restore_mana": (0, 25, False), "healing": (9, 30, False),
                          "star_healing": (0, 15, False), "resistance": (9, 20, False),
                          "teleport": (15, 40, False)})
        self.assertTrue(rows["equipment"]["ready"])
        self.assertTrue(rows["resist_curse"]["ready"])
        angband_finale.observe(policy, board)
        self.assertFalse(angband_finale.lifted(policy))
        self.assertEqual(angband_cap.cap(DUNGEON_ANGBAND, policy), 95)
        self.assertTrue(angband_cap.capped_at(DUNGEON_ANGBAND, 96, policy))

    def test_a_ready_board_lifts_the_cap_until_the_next_town(self):
        policy = self.policy
        angband_finale.observe(policy, self.stocked())
        self.assertTrue(angband_finale.lifted(policy))
        self.assertIsNone(angband_cap.cap(DUNGEON_ANGBAND, policy))
        self.assertFalse(angband_cap.capped_at(DUNGEON_ANGBAND, 99, policy))
        self.assertEqual(angband_cap.cap(DUNGEON_ANGBAND), 95)  # no policy: the cap as before
        floor = self.dungeon(96)
        self.assertFalse(angband_cap.capped(floor, 97, policy))
        self.assertFalse(angband_cap.climbing(floor, policy))
        # A dungeon board keeps the town's latch, whatever it carries now.
        angband_finale.observe(policy, floor)
        self.assertTrue(angband_finale.lifted(policy))
        # The next town board measures again.
        angband_finale.observe(policy, self.town)
        self.assertFalse(angband_finale.lifted(policy))

    def test_a_resist_curse_is_required(self):
        policy, stocked = self.policy, self.stocked()
        sources = {name: stocked.player.ability_sources[name]
                   for name in stocked.player.ability_sources if name != "resist_curse"}
        without = replace(stocked, player=replace(
            stocked.player, abilities=stocked.player.abilities - {"resist_curse"},
            ability_sources=AbilitySources(sources)))
        angband_finale.observe(policy, without)
        self.assertFalse(angband_finale.lifted(policy))
        self.assertEqual(angband_finale.memory(policy).report["resist_curse"], {"ready": False})

    # -- (b) the supplies -------------------------------------------------------------

    def test_b_carry_kept_taken_and_bought(self):
        policy, board = self.policy, self.town
        pack = {(item.tval, item.sval): item for item in board.inventory}
        healing = replace(pack[(TVAL_POTION, SV_POTION_HEALING)], count=35)
        big = replace(board, inventory=[healing if item is pack[(TVAL_POTION, SV_POTION_HEALING)]
                                        else item for item in board.inventory])
        # Kept: 30 of a stack of 35 (the retention authority every sale and deposit asks).
        self.assertEqual(policy._retention_reservation(big, healing), 30)
        # The Teleportation scrolls: 40 of 45, before the readiness (the supply ledger's own
        # departure count holds 40 only once the dive is decided).
        scrolls = replace(pack[(TVAL_SCROLL, SV_SCROLL_TELEPORT)], count=45)
        many = replace(board, inventory=[scrolls if item is pack[(TVAL_SCROLL, SV_SCROLL_TELEPORT)]
                                         else item for item in board.inventory])
        self.assertEqual(policy._retention_reservation(many, scrolls), 40)
        star = replace(healing, sval=SV_POTION_STAR_HEALING, count=1)
        # Taken from Home and bought up to the counts (the shared potion target).
        self.assertEqual(policy._carry_strategy_potion_target(board, star),
                         (15, angband_finale.RETENTION_BRANCH))
        self.assertEqual(policy._carry_strategy_potion_target(board, healing),
                         (30, angband_finale.RETENTION_BRANCH))
        mana = replace(healing, sval=SV_POTION_RESTORE_MANA, count=1)
        self.assertEqual(policy._carry_strategy_potion_target(board, mana)[0], 25)
        # The Home-shelved kinds of the table are carried instead.
        self.assertTrue(consumable_policy.carry_required(policy, board, star))
        self.assertTrue(consumable_policy.carry_required(policy, board, mana))
        teleport = pack[(TVAL_SCROLL, SV_SCROLL_TELEPORT)]
        self.assertEqual(policy._procurement_missing_amount(board, teleport), 25)

    def test_b_black_market_star_healing(self):
        policy, page = self.policy, self.black_market
        self.assertEqual(page.store.store_type, STORE_BLACK)
        ware = replace(page.store.items[0], name="*体力回復*の薬", tval=TVAL_POTION,
                       sval=SV_POTION_STAR_HEALING, count=3, price=12000,
                       letter=chr(ord("a") + len(page.store.items)))
        shelf = replace(page, store=replace(page.store, items=[ware]),
                        player=replace(page.player, gold=10_000_000))
        picked = policy._black_market_optional_purchase(shelf)
        self.assertEqual((picked.tval, picked.sval), (TVAL_POTION, SV_POTION_STAR_HEALING))
        stocked = self.stocked(shelf)
        self.assertIsNone(policy._black_market_optional_purchase(stocked))

    def test_b_teleport_units_from_the_spare_gold(self):
        policy, board = self.policy, self.town
        reserve = policy._full_departure_resupply_reserve(board)
        self.assertIsNotNone(reserve)
        ware = replace(self.black_market.store.items[0], name="テレポートの巻物", tval=TVAL_SCROLL,
                       sval=SV_SCROLL_TELEPORT, count=30, price=150)
        rich = replace(board, player=replace(board.player, gold=reserve + 150 * 30))
        self.assertEqual(policy._angband_finale_purchase_units(rich, ware), 25)
        poor = replace(board, player=replace(board.player, gold=reserve + 150 * 3))
        self.assertEqual(policy._angband_finale_purchase_units(poor, ware), 3)
        self.assertEqual(policy._angband_finale_purchase_units(self.stocked(rich), ware), 0)

    # -- the weight (answer 3) ----------------------------------------------------------

    def test_b_overweight_only_above_plus_25(self):
        policy, board = self.policy, self.town
        limit = policy._inventory_weight_limit(board)
        self.assertEqual((limit, policy._inventory_weight(board), board.player.speed), (1950, 2136, 135))
        # Recorded: +25 is not above +25, so 2136 > 1950 stays overweight.
        self.assertTrue(policy._inventory_overweight(board))
        fast = replace(board, player=replace(board.player, speed=140))
        # Speed 140 unslowed (2136 slows nothing: (2136-1950)//390 = 0): four steps of 390 keep
        # it at +26 or above, so the limit is 1950 + 5 x 390 - 1.
        self.assertEqual(angband_finale.weight_limit(policy, fast, limit), 3899)
        self.assertFalse(policy._inventory_overweight(fast))

        def weighing(total):
            """The pack at ``total`` and the board's speed as the game shows it then: 140 less
            the slowdown (player-speed.cpp calc_speed_bonus_by_weight)."""
            first = fast.inventory[0]
            extra = total - policy._inventory_weight(fast)
            slowed = 140 - angband_finale.slowdown(total, limit)
            return replace(fast, player=replace(fast.player, speed=slowed),
                           inventory=[replace(first, weight=first.weight + extra), *fast.inventory[1:]])
        self.assertFalse(policy._inventory_overweight(weighing(3899)))
        self.assertTrue(policy._inventory_overweight(weighing(3900)))


if __name__ == "__main__":
    unittest.main()
