"""The 99F/100F readiness, the supply plan and the weight (angband_finale).

Owner 2026-11-20 (the 99F/100F directive, its answers, and the answers to the report's questions;
angband_finale's docstring): the 95F cap lifts when a town board finds the Restore Mana target,
Healing 30, *Healing* 15, Resistance 20, Teleportation 40 and the absorbed Stone to Mud
(「取り込んだ岩石溶解を条件に入れる」) and the equipment conditions (speed, the resistances,
telepathy, 「呪力耐性も要求する」, 「耐盲目か耐閃光を条件に入れる」).  「準備がそろってから」: the
readiness judges whether the owned gear (worn, carried, at Home) CAN meet the conditions, and
「上限を外す時に初めて着け替える」: the dedicated loadout, the carry and the weight allowance hold only
on the visit that switches to 99F/100F (the supplies owned and the conditions met by the owned
gear), the lift once the counts are in the pack and the conditions worn.  (The small-floor option:
tests/test_angband_finale_battle_1120_recorded.py.)

Recorded: n1-b life-411's town arrival of 2026-11-20 03:32:34 (tests/fixtures/
n1b-411-home-closed-pending-1120): Lv50 Magic-Eater, Angband recall depth 95, speed 135, carrying
9 Healing, 9 Resistance, 15 Teleportation, no *Healing* and no Restore Mana; its Home census holds
207 Healing, 359 Resistance and one Restore Mana (target 25); Stone to Mud absorbed 99; weight 2136
over its limit 1950; telepathy, resist curse, resist blindness and light worn.  Its Black Market
page is row 80.  The dungeon boards are n1-b's recorded Angband 99F arrival
(tests/fixtures/n1b-411-angband-cap-1119).

DECLARED CONSTRUCTED:
* ``home_stocked``: the Home census with a *Healing* (15), a Restore Mana (25) and a Teleportation
  (25) stack added (copies of a recorded potion row);
* ``pack_stocked``: the recorded town board with the carried stacks set to the finale's counts
  (the recorded Healing, Resistance and Teleportation stacks raised, a *Healing* and a Restore Mana
  stack added by copying the Healing stack's row);
* ``without``: a board without the abilities a test names (abilities and their sources);
* ``chosen``: the read-only search's result (``_angband_finale_feasibility``): the worn
  loadout's preparation with its chosen set replaced by the worn set without the items that carry
  the flag a test names (or none of them removed);
* the Stone to Mud row of the displayed wand list with the absorbed count a test names;
* ``dungeon``: the recorded 99F board at the level asked;
* the Black Market wares (the page's first, changed to *Healing*, Teleportation, Stone to Mud);
* ``latch``: the board observed as an arrival (the latch's ``in_town`` set as after a dungeon
  board) unless a test says it is a later board of the visit;
* the speed of the weight test (140 unslowed, less the slowdown of the weight asked) and its pack
  weights (one stack's weight changed); the latch's stages where a test says so.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_cap, angband_finale, consumable_policy, me_device_policy
from hengbot.equipment_optimizer import EvaluatedLoadout, Loadout
from hengbot.model import (
    DUNGEON_ANGBAND, STORE_BLACK, AbilitySources, SV_POTION_HEALING, SV_POTION_RESISTANCE,
    SV_POTION_RESTORE_MANA, SV_POTION_STAR_HEALING, SV_SCROLL_TELEPORT, SV_WAND_STONE_TO_MUD,
    TVAL_POTION, TVAL_SCROLL, TVAL_WAND, parse_snapshot,
)
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-home-closed-pending-1120"
FLOOR_FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-angband-cap-1119"
BLACK_MARKET_ROW = 80
HEALING, STAR = (TVAL_POTION, SV_POTION_HEALING), (TVAL_POTION, SV_POTION_STAR_HEALING)
MANA, TELEPORT = (TVAL_POTION, SV_POTION_RESTORE_MANA), (TVAL_SCROLL, SV_SCROLL_TELEPORT)
COUNTS = {HEALING: 30, STAR: 15, (TVAL_POTION, SV_POTION_RESISTANCE): 20, TELEPORT: 40, MANA: 25}
TR_RES_CURSE = 148


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

    # -- the constructed state -----------------------------------------------------------

    def home_stocked(self):
        """DECLARED CONSTRUCTED (the module docstring)."""
        policy = self.policy
        potion = next(item for item in policy._home_knowledge_items if item.tval == TVAL_POTION)
        policy._home_knowledge_items = (
            *policy._home_knowledge_items,
            replace(potion, sval=SV_POTION_STAR_HEALING, count=15, name="*体力回復*の薬"),
            replace(potion, sval=SV_POTION_RESTORE_MANA, count=25, name="魔力復活の薬"),
            replace(potion, tval=TVAL_SCROLL, sval=SV_SCROLL_TELEPORT, count=25, name="テレポートの巻物"))

    def pack_stocked(self, board=None):
        board = board or self.town
        healing = next(item for item in board.inventory if (item.tval, item.sval) == HEALING)
        pack = [replace(item, count=COUNTS[(item.tval, item.sval)])
                if (item.tval, item.sval) in COUNTS else item for item in board.inventory]
        pack.append(replace(healing, slot="x", sval=SV_POTION_STAR_HEALING, count=15, name="*体力回復*の薬"))
        pack.append(replace(healing, slot="y", sval=SV_POTION_RESTORE_MANA, count=25, name="魔力復活の薬"))
        return replace(board, inventory=pack)

    def without(self, board, names):
        player = board.player
        sources = {name: player.ability_sources[name] for name in player.ability_sources
                   if name not in names}
        return replace(board, player=replace(player, abilities=player.abilities - set(names),
                                             ability_sources=AbilitySources(sources)))

    def chosen_without(self, flag, *, name="_angband_finale_feasibility"):
        """A search's chosen set: the worn set without its items that carry ``flag`` (the
        read-only search's, ``_angband_finale_feasibility``, by default)."""
        preparation = self.arrival._equipment_optimization_preparation  # the recorded search
        current = preparation.current
        slots = tuple((slot, item) for slot, item in current.slots if flag is None or flag not in item.flags)
        best = preparation.result.best
        setattr(self.policy, name, replace(
            preparation, result=replace(preparation.result,
                                        best=EvaluatedLoadout(Loadout(slots, current.hand_mode), best.metrics))))

    def stone_to_mud_count(self, count):
        from hengbot import me_capability
        lists = dict(self.policy._me_device_lists)
        turn, rows = lists["wand"]
        listed = me_capability.names("wand", SV_WAND_STONE_TO_MUD)
        lists["wand"] = (turn, [dict(row, max=count, current=count) if row.get("name") in listed else row
                                for row in rows])
        self.policy._me_device_lists = lists
        record = me_capability.recorded(self.policy)
        for key in list(record):
            if key == me_capability.record_key("wand", SV_WAND_STONE_TO_MUD):
                record[key] = count

    def dungeon(self, level):
        raw = copy.deepcopy(self.raw)
        raw["floor"] = {**raw["floor"], "level": level}
        return parse_snapshot(raw, self.policy._monrace_knowledge)

    def latch(self, board, *, arrival=True):
        """The board observed as the visit's first town board (``arrival``, after a dungeon
        board), else as a later board of the same visit."""
        angband_finale.memory(self.policy).in_town = not arrival
        angband_finale.observe(self.policy, board)
        held = angband_finale.memory(self.policy)
        return held.supplied, held.switching, held.ready

    # -- (a) the readiness gate and the cap's lift --------------------------------------

    def test_a_recorded_board_is_short_and_keeps_the_cap(self):
        policy, board = self.policy, self.town
        rows = angband_finale.readiness(policy, board)
        self.assertEqual({name: (row["measured"], row["ready"]) for name, row in rows["owned"].items()},
                         {"restore_mana": (1, False), "healing": (216, True), "star_healing": (0, False),
                          "resistance": (368, True), "teleport": (15, False), "stone_to_mud": (99, True)})
        self.assertEqual(rows["carried"]["healing"]["measured"], 9)
        self.assertEqual((rows["equipment_owned"], rows["equipment_worn"]),
                         ({"missing": [], "ready": True}, {"missing": [], "ready": True}))
        self.assertEqual(self.latch(board), (False, False, False))
        self.assertEqual(angband_cap.cap(DUNGEON_ANGBAND, policy), 95)
        self.assertTrue(angband_cap.capped_at(DUNGEON_ANGBAND, 96, policy))

    def test_a_the_stages(self):
        """Owned at Home with the gear worn: the switching visit (loadout, carry, weight);
        carried: the lift.  Short of the supplies: no switch (the 95F rules as ever)."""
        self.home_stocked()
        self.assertEqual(self.latch(self.town), (True, True, False))
        self.assertEqual(angband_cap.cap(DUNGEON_ANGBAND, self.policy), 95)
        self.assertEqual(self.latch(self.pack_stocked()), (True, True, True))
        self.assertIsNone(angband_cap.cap(DUNGEON_ANGBAND, self.policy))
        self.assertFalse(angband_cap.capped_at(DUNGEON_ANGBAND, 99, self.policy))
        self.assertEqual(angband_cap.cap(DUNGEON_ANGBAND), 95)  # no policy: the cap as before
        floor = self.dungeon(96)
        self.assertFalse(angband_cap.capped(floor, 97, self.policy))
        self.assertFalse(angband_cap.climbing(floor, self.policy))
        angband_finale.observe(self.policy, floor)  # a dungeon board keeps the town's latch
        self.assertTrue(angband_finale.lifted(self.policy))
        self.policy._home_knowledge_items = self.arrival._home_knowledge_items
        self.assertEqual(self.latch(self.town), (False, False, False))

    def test_a_the_switch_is_decided_on_arrival(self):
        """「上限を外す時に初めて着け替える」, decided as the visit begins: supplies completed in the
        middle of a visit switch nothing until the next arrival; a resumed process (no board
        seen yet) switches nothing either."""
        self.assertEqual(self.latch(self.town), (False, False, False))
        self.home_stocked()
        self.assertEqual(self.latch(self.town, arrival=False), (True, False, False))
        self.assertFalse(angband_finale.switching(self.policy))
        self.assertEqual(self.latch(self.town), (True, True, False))
        fresh = copy.deepcopy(self.policy)
        fresh._angband_finale = angband_finale.Memory()
        angband_finale.observe(fresh, self.town)
        self.assertFalse(angband_finale.switching(fresh))

    def test_a_resist_curse_and_blindness_or_light(self):
        """「呪力耐性も要求する」 and 「耐盲目か耐閃光を条件に入れる」 on the board worn."""
        stocked = self.pack_stocked()
        self.home_stocked()
        for names, missing in ((("resist_curse",), "resist_curse"),
                               (("resist_blind", "resist_lite"), "resist_blind|resist_lite")):
            with self.subTest(missing=missing):
                board = self.without(stocked, names)
                self.assertEqual(self.latch(board)[2], False)
                self.assertIn(missing, angband_finale.memory(self.policy).report["equipment_worn"]["missing"])
        # Either one is enough.
        self.assertTrue(self.latch(self.without(stocked, ("resist_blind",)))[2])
        self.assertTrue(self.latch(self.without(stocked, ("resist_lite",)))[2])

    def test_a_the_owned_gear_is_judged(self):
        """「現在の装備と自宅の品で満たせるか」, judged by the read-only search before the switch
        (「上限を外す時に初めて着け替える」): a board without resist curse switches when that search's
        set has it, not when only the worn loadout's search would."""
        self.home_stocked()
        board = self.without(self.pack_stocked(), ("resist_curse",))
        self.assertIsNone(getattr(self.policy, "_angband_finale_feasibility", None))
        self.assertEqual(self.latch(board), (True, False, False))  # no search yet: the board's
        self.assertTrue(angband_finale.feasibility_due(self.policy, board))
        self.chosen_without(None)
        self.assertEqual(self.latch(board), (True, True, False))
        self.assertFalse(angband_finale.feasibility_due(self.policy, board))
        self.policy._angband_finale_feasibility = None
        angband_finale.memory(self.policy).switching = False
        self.chosen_without(TR_RES_CURSE)
        self.assertEqual(self.latch(board), (True, False, False))
        self.assertIn("resist_curse", angband_finale.memory(self.policy).report["equipment_owned"]["missing"])
        # The worn loadout's own search does not stand in for it before the switch.
        self.policy._angband_finale_feasibility = None
        self.assertEqual(self.latch(board), (True, False, False))

    def test_a_the_worn_loadout_switches_only_on_the_switch(self):
        """「上限を外す時に初めて着け替える」: before the switch the worn loadout's search has the
        ordinary inputs (the same key as with no supplies owned) and the read-only search in the
        finale's rank runs beside it; on the switching visit the worn loadout's own search is the
        finale's and no second search runs."""
        board = self.without(self.town, ("resist_curse",))  # the supplies at Home only
        plain = copy.deepcopy(self.arrival)
        angband_finale.observe(plain, board)
        plain._prepare_equipment_optimization(board)
        self.home_stocked()
        self.assertEqual(self.latch(board), (True, False, False))
        self.policy._prepare_equipment_optimization(board)
        self.assertEqual(self.policy._equipment_optimizer_input_key, plain._equipment_optimizer_input_key)
        self.assertIsNotNone(self.policy._angband_finale_feasibility)
        self.assertIsNone(getattr(plain, "_angband_finale_feasibility", None))
        self.chosen_without(None)
        self.assertEqual(self.latch(board), (True, True, False))
        self.policy._prepare_equipment_optimization(board)
        self.assertNotEqual(self.policy._equipment_optimizer_input_key, plain._equipment_optimizer_input_key)
        self.assertIsNone(self.policy._angband_finale_feasibility)

    def test_a_stone_to_mud_absorbed(self):
        """「取り込んだ岩石溶解を条件に入れる」: ten absorbed, bought and absorbed below it."""
        self.home_stocked()
        self.stone_to_mud_count(9)
        self.assertEqual(self.latch(self.pack_stocked()), (False, False, False))
        page = self.black_market
        ware = replace(page.store.items[0], name="岩石溶解の魔法棒", tval=TVAL_WAND,
                       sval=SV_WAND_STONE_TO_MUD, count=1, price=500, aware=True)
        rich = replace(page, store=replace(page.store, items=[ware]),
                       player=replace(page.player, gold=10_000_000))
        self.assertTrue(me_device_policy.purchase_wanted(self.policy, rich, ware))
        self.stone_to_mud_count(10)
        self.assertEqual(self.latch(self.pack_stocked()), (True, True, True))
        self.assertFalse(me_device_policy.purchase_wanted(self.policy, rich, ware))

    # -- (b) the supplies -------------------------------------------------------------

    def test_b_carry_only_on_the_switch(self):
        policy, board = self.policy, self.town
        pack = {(item.tval, item.sval): item for item in board.inventory}
        healing = replace(pack[HEALING], count=35)
        star = replace(healing, sval=SV_POTION_STAR_HEALING, count=1)
        self.assertIsNone(angband_finale.carry_target(policy, board, star))  # 「準備がそろってから」
        self.home_stocked()
        self.latch(board)
        self.assertTrue(angband_finale.switching(policy))
        big = replace(board, inventory=[healing if item is pack[HEALING] else item
                                        for item in board.inventory])
        # Kept: 30 of a stack of 35 (the retention authority every sale and deposit asks).
        self.assertEqual(policy._retention_reservation(big, healing), 30)
        scrolls = replace(pack[TELEPORT], count=45)
        many = replace(board, inventory=[scrolls if item is pack[TELEPORT] else item
                                         for item in board.inventory])
        self.assertEqual(policy._retention_reservation(many, scrolls), 40)
        # Taken from Home and bought up to the counts (the shared potion target).
        self.assertEqual(policy._carry_strategy_potion_target(board, star),
                         (15, angband_finale.RETENTION_BRANCH))
        self.assertEqual(policy._carry_strategy_potion_target(board, healing),
                         (30, angband_finale.RETENTION_BRANCH))
        mana = replace(healing, sval=SV_POTION_RESTORE_MANA, count=1)
        self.assertEqual(policy._carry_strategy_potion_target(board, mana)[0], 25)
        self.assertTrue(consumable_policy.carry_required(policy, board, star))
        self.assertTrue(consumable_policy.carry_required(policy, board, mana))
        self.assertEqual(policy._procurement_missing_amount(board, pack[TELEPORT]), 25)

    def test_b_black_market_star_healing(self):
        policy, page = self.policy, self.black_market
        self.assertEqual(page.store.store_type, STORE_BLACK)
        ware = replace(page.store.items[0], name="*体力回復*の薬", tval=TVAL_POTION,
                       sval=SV_POTION_STAR_HEALING, count=3, price=12000,
                       letter=chr(ord("a") + len(page.store.items)))
        shelf = replace(page, store=replace(page.store, items=[ware]),
                        player=replace(page.player, gold=10_000_000))
        picked = policy._black_market_optional_purchase(shelf)
        self.assertEqual((picked.tval, picked.sval), STAR)
        self.home_stocked()  # 15 at Home: owned, nothing more to buy
        self.assertIsNone(policy._black_market_optional_purchase(shelf))

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
        self.home_stocked()  # 25 more at Home: 40 owned
        self.assertEqual(policy._angband_finale_purchase_units(rich, ware), 0)

    # -- the weight (answer 3, 「準備がそろってから」) -------------------------------------------

    def test_b_overweight_only_above_plus_25_on_the_switch(self):
        policy, board = self.policy, self.town
        limit = policy._inventory_weight_limit(board)
        self.assertEqual((limit, policy._inventory_weight(board), board.player.speed), (1950, 2136, 135))
        fast = replace(board, player=replace(board.player, speed=140))
        self.assertTrue(policy._inventory_overweight(fast))  # not stocked: the limit as before
        self.home_stocked()
        self.latch(board)
        # Recorded: +25 is not above +25, so 2136 > 1950 stays overweight.
        self.assertTrue(policy._inventory_overweight(board))
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
