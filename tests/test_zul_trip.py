"""The Zul trip: a Lv30+ character with a mutation is cured at Zul (owner 2026-11-07).

Owner: 「Lv.30以上のキャラクタが突然変異を得た場合、ズルに直しに行く処理を作る。
これは荒野と広域モードを使用しない処理の例外である。」  Which: any curable mutation;
when: the next ordinary town arrival, ahead of the other errands; how many: all,
fundraising first when the gold is short; route: the inn to the visited town nearest
Zul, the global map on foot, and back.

Recorded: n1-a life-422's last Outpost board before its inn trip
(tests/fixtures/quest-stops-20261030.json.gz, q2 ``outpost_board``; a warrior that
eats device charges, Telmora, Morivant and Angwil listed).  DECLARED CONSTRUCTED on
it: the level raised to 35 (the recorded character is Lv24), the observed mutation
signature (no character sheet is part of the capture), the levitation source, the
gold, a carried or stored Ring of Levitation and the shelves seen this stay where a
test names them.  The global map, the Zul board and the ambush board are
CONSTRUCTED from lib/edit (WildernessDefinition.jsonc, towns/05_Zul.jsonc); no live
screen of the global map, of an ambush or of building 14 has been captured.
Every decision goes through the public chooser ``policy.choose_key``.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
from dataclasses import replace
from math import ceil
from pathlib import Path
import unittest

from policy_fixtures import grid, hostile, item, player
from hengbot import zul_trip
from hengbot.home_errand import HomeErrandState
from hengbot.input_executor import ScreenKind
from hengbot.model import (
    GridState, Position, Snapshot, StoreItem, StoreState, STORE_BLACK, STORE_MAGIC, parse_snapshot,
)
from hengbot.observed_input import compile_observed_input
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import ZUL_TOWN_ID
from hengbot.town_maps import find_town_map, parse_town_map
from hengbot.wilderness_map import WildernessMap, find_wilderness_definition, load_wilderness_map
# The module, not the class: a TestCase bound here would run its tests again.
from tests import test_q2_tower_recharge_recorded as q2_town

GAME = Path("C:/hengband")
ANGWIL = 3
MUTATION = 3  # PlayerMutationType::SPIT_ACID: any curable one
MOVES = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
         "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


def wilderness():
    return load_wilderness_map(find_wilderness_definition(GAME))


class RouteFactsTest(unittest.TestCase):
    """The route table read from lib/edit/WildernessDefinition.jsonc."""

    def test_each_town_to_zul_matches_the_static_map(self):
        routes = zul_trip._town_routes(wilderness())
        self.assertEqual({town: (found.steps, found.shallow) for town, found in routes.items()},
                         {0: (87, 1), 1: (43, 1), 2: (48, 1), 3: (19, 1)})
        rows = wilderness().rows
        angwil = routes[ANGWIL]
        cells = [rows[y][x] for y, x in angwil.cells]
        self.assertEqual((cells[0], cells[-1]), ("4", "5"))
        self.assertEqual(sum(cell == "^" for cell in cells), 3)
        self.assertFalse(set(cells) & {"~", "&", "$", "#"})

    def test_without_levitation_zul_is_out_of_reach(self):
        wmap = wilderness()
        zul = zul_trip.town_cell(wmap, ZUL_TOWN_ID)
        for town in range(4):
            self.assertIsNone(zul_trip.route(wmap, zul_trip.town_cell(wmap, town), zul, levitation=False))

    def test_deep_water_and_lava_never_shallow_water_least(self):
        wmap = WildernessMap((
            "#########",
            "#1~~~~~5#",
            "#._..._.#",
            "#.$&$&..#",
            "#.......#",
            "#########",
        ))
        found = zul_trip.route(wmap, (1, 1), (1, 7), levitation=True)
        cells = [wmap.rows[y][x] for y, x in found.cells]
        self.assertFalse(set(cells) & {"~", "&", "$"})
        # The dry detour through row 4 enters no shallow water.
        self.assertEqual(found.shallow, 0)
        self.assertGreater(found.steps, 6)

    def test_mountain_needs_levitation(self):
        wmap = WildernessMap(("#####", "#1^2#", "#.~.#", "#####"))
        self.assertIsNone(zul_trip.route(wmap, (1, 1), (1, 3), levitation=False))
        self.assertEqual(zul_trip.route(wmap, (1, 1), (1, 3), levitation=True).keys, "66")


class ZulTripTownTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        q2_town.Q2TowerRechargeRecordedTest.setUpClass.__func__(cls)
        cls.wmap = wilderness()

    def raw_board(self, *, level=35, gold=None, levitation=True):
        raw = copy.deepcopy(self.q2["outpost_board"])
        raw["player"]["level"] = level
        if gold is not None:
            raw["player"]["gold"] = gold
        source = raw["player"]["ability_sources"].setdefault("levitation", {})
        source["equipment"] = levitation
        return raw

    def policy(self, raw, *, mutations=(MUTATION,)):
        policy = q2_town.Q2TowerRechargeRecordedTest.policy(self, raw)
        policy._wilderness_map = self.wmap
        policy._mutation_signature = tuple(mutations)
        return policy

    def board(self, raw):
        return parse_snapshot(copy.deepcopy(raw), self.monraces)

    @staticmethod
    def ring_row(raw, slot="r"):
        row = copy.deepcopy(raw["inventory"][0])
        row.update(slot=slot, name="浮遊の指輪", tval=zul_trip.TVAL_RING,
                   sval=zul_trip.SV_RING_LEVITATION, count=1, aware=True, known=True,
                   is_equipment=True, charges=0, pval=0)
        return row

    # -- the trigger ---------------------------------------------------------

    def test_lv30_with_a_mutation_takes_the_inn_to_angwil(self):
        raw = self.raw_board()
        policy = self.policy(raw)
        key = policy.choose_key(self.board(raw))
        self.assertTrue(policy.last_reason.startswith(zul_trip.TRAVEL_REASON), (key, policy.last_reason))
        self.assertEqual(zul_trip.start_town(policy, self.board(raw)), ANGWIL)

    def test_below_lv30_nothing(self):
        raw = self.raw_board(level=29)
        policy = self.policy(raw)
        policy.choose_key(self.board(raw))
        self.assertFalse(policy.last_reason.startswith(zul_trip.REASON), policy.last_reason)

    def test_no_mutation_nothing(self):
        raw = self.raw_board()
        policy = self.policy(raw, mutations=())
        policy.choose_key(self.board(raw))
        self.assertFalse(policy.last_reason.startswith(zul_trip.REASON), policy.last_reason)

    def test_the_lucky_white_aura_is_not_curable(self):
        raw = self.raw_board()
        raw["player"]["personality_id"] = zul_trip.PERSONALITY_LUCKY
        policy = self.policy(raw, mutations=(zul_trip.GOOD_LUCK,))
        policy.choose_key(self.board(raw))
        self.assertFalse(policy.last_reason.startswith(zul_trip.REASON), policy.last_reason)
        # Anyone else's white aura is cured (cmd-building.cpp resets it for the Lucky only).
        raw["player"]["personality_id"] = 0
        other = self.policy(raw, mutations=(zul_trip.GOOD_LUCK,))
        other.choose_key(self.board(raw))
        self.assertTrue(other.last_reason.startswith(zul_trip.TRAVEL_REASON), other.last_reason)

    # -- gold ----------------------------------------------------------------

    def test_short_gold_fundraises_first(self):
        raw = self.raw_board(gold=4000)
        policy = self.policy(raw)
        board = self.board(raw)
        needed = zul_trip.gold_needed(policy, board, ANGWIL)
        policy.choose_key(board)
        # The WAIT is stepped off the entrance the board stands on (a post-decision rewrite).
        self.assertTrue(policy.last_reason.endswith(f"{zul_trip.FUNDRAISE_REASON}:{needed}"),
                        policy.last_reason)
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertEqual(policy._supply_stockout_gold_target, needed)
        self.assertGreaterEqual(needed, zul_trip.CURE_OTHER_PRICE + 2 * 500)

    def test_every_curable_mutation_is_paid_for(self):
        raw = self.raw_board()
        policy = self.policy(raw, mutations=(1, 2, 3))
        board = self.board(raw)
        self.assertEqual(zul_trip.gold_needed(policy, board, ANGWIL)
                         - zul_trip.gold_needed(self.policy(raw), board, ANGWIL),
                         2 * zul_trip.CURE_OTHER_PRICE)

    # -- levitation ----------------------------------------------------------

    def test_carried_ring_is_put_on(self):
        raw = self.raw_board(levitation=False)
        raw["inventory"].append(self.ring_row(raw))
        policy = self.policy(raw)
        key = policy.choose_key(self.board(raw))
        self.assertEqual(policy.last_reason, zul_trip.WEAR_REASON)
        self.assertTrue(key.startswith("w"), repr(key))

    def test_ring_in_home_is_taken_out(self):
        raw = self.raw_board(levitation=False)
        policy = self.policy(raw)
        board = self.board(raw)
        ring = replace(board.inventory[0], slot="a", name="浮遊の指輪", tval=zul_trip.TVAL_RING,
                       sval=zul_trip.SV_RING_LEVITATION, count=1, aware=True, known=True)
        policy.consume_home_knowledge((ring,))
        policy.choose_key(board)
        errand = policy._home_errand
        self.assertIsNotNone(errand.request)
        self.assertEqual(errand.request.purpose, zul_trip.HOME_PURPOSE)
        self.assertNotEqual(errand.state, HomeErrandState.IDLE)

    def test_no_ring_unseen_shelf_goes_to_the_magic_shop(self):
        raw = self.raw_board(levitation=False)
        policy = self.policy(raw)
        board = self.board(raw)
        key = policy.choose_key(board)
        self.assertTrue(policy.last_reason.startswith("shop:"), (key, policy.last_reason))
        self.assertIsNone(zul_trip.state(policy).failure)

    def seen(self, policy, board, store, items):
        policy._town_supplier_stock[store] = StoreState(store, list(items))
        policy._town_supplier_stock_observations[store] = (policy._effective_town_id(board), board.turn)

    def test_both_shelves_without_a_ring_skip_this_stay(self):
        raw = self.raw_board(levitation=False)
        policy = self.policy(raw)
        board = self.board(raw)
        self.seen(policy, board, STORE_MAGIC, ())
        self.seen(policy, board, STORE_BLACK, ())
        key = policy.choose_key(board)
        record = zul_trip.state(policy)
        self.assertEqual(record.failure, "no-levitation")
        self.assertEqual(record.closed_epoch, policy._town_visit_epoch)
        self.assertFalse(policy.last_reason.startswith(zul_trip.REASON), (key, policy.last_reason))
        # The trip's food rows close with it: the visit departs as usual.
        self.assertEqual(zul_trip.extra_food_items(policy, board), 0)

    def test_a_ring_on_the_black_market_is_bought(self):
        raw = self.raw_board(levitation=False)
        policy = self.policy(raw)
        board = self.board(raw)
        ring = StoreItem("c", "浮遊の指輪", 1, zul_trip.TVAL_RING, zul_trip.SV_RING_LEVITATION, price=2000)
        self.seen(policy, board, STORE_MAGIC, ())
        self.seen(policy, board, STORE_BLACK, (ring,))
        policy.choose_key(board)
        self.assertTrue(policy.last_reason.startswith("shop:"), policy.last_reason)
        inside = replace(board, store=StoreState(STORE_BLACK, [ring]))
        self.assertTrue(zul_trip.shopping(policy, inside))
        rungs = policy._matching_live_purchase_rungs(inside, ring)
        self.assertEqual([match.rung_id for match in rungs][:1], [zul_trip.BUY_RUNG])
        # The page is the trip's alone while it sells the ring (as the staff sequence's).
        from hengbot.purchase_rungs import PurchaseContext
        self.assertEqual([rung.rung_id for rung in policy._purchase_rungs(PurchaseContext(inside))],
                         [zul_trip.BUY_RUNG])

    # -- food ----------------------------------------------------------------

    def test_food_is_twice_the_round_trip_on_top_of_the_usual(self):
        raw = self.raw_board()
        policy = self.policy(raw)
        board = self.board(raw)
        per_step = zul_trip.food_per_step(board)
        # slow_digest (the board's ring): 10 - 5 every 50 game turns, 1320 game turns a step.
        self.assertEqual(per_step, ceil(1320 / 50 * 5))
        extra = ceil(2 * 2 * 19 * per_step / zul_trip.FOOD_PER_ITEM)
        self.assertEqual(zul_trip.extra_food_items(policy, board), extra)
        without = self.policy(raw, mutations=())
        usual = without._supply_ledger(board, 1)["food"].required_departure
        self.assertEqual(policy._supply_ledger(board, 1)["food"].required_departure, usual + extra)

    # -- the end of the walk -------------------------------------------------

    def test_back_in_the_start_town_the_paid_mutations_are_gone(self):
        raw = self.raw_board()
        raw["floor"]["town_id"] = ANGWIL
        policy = self.policy(raw, mutations=(1, 3))
        board = self.board(raw)
        record = zul_trip.state(policy)
        record.active, record.start_town, record.returning = True, ANGWIL, True
        record.curable, record.cured = (1, 3), 2
        policy.choose_key(board)
        self.assertEqual(policy._mutation_signature, ())
        self.assertFalse(zul_trip.trip_active(policy))
        self.assertFalse(policy.last_reason.startswith(zul_trip.REASON), policy.last_reason)


class GlobalMapTest(unittest.TestCase):
    """CONSTRUCTED global-map boards (gridless, the measured 99x66 command space)."""

    @classmethod
    def setUpClass(cls):
        cls.wmap = wilderness()

    def policy(self, *, returning=False):
        policy = HengbotPolicy(wilderness_map=self.wmap)
        record = zul_trip.state(policy)
        record.active, record.start_town, record.returning = True, ANGWIL, returning
        record.curable, record.price = (MUTATION,), 5000
        return policy

    def board(self, cell, *, levitation=True, **player_fields):
        abilities = frozenset({"levitation"}) if levitation else frozenset()
        return Snapshot(
            player(*cell, hp=400, max_hp=400, level=35, abilities=abilities, **player_fields),
            {}, [], floor_key=(0, 0, 0), width=99, height=66, town_flag=False,
            town_id=-1, town_index=0)

    def walk(self, policy, start, goal_reason=zul_trip.ENTER_TOWN_REASON):
        cell, cells = start, [start]
        for _step in range(200):
            key = policy.choose_key(self.board(cell))
            if policy.last_reason == goal_reason:
                self.assertEqual(key, ">")
                return cells
            self.assertEqual(policy.last_reason, zul_trip.GLOBAL_STEP_REASON)
            dy, dx = MOVES[key]
            cell = (cell[0] + dy, cell[1] + dx)
            cells.append(cell)
        self.fail("no arrival")

    def test_angwil_to_zul_and_back(self):
        angwil, zul = zul_trip.town_cell(self.wmap, ANGWIL), zul_trip.town_cell(self.wmap, ZUL_TOWN_ID)
        out = self.walk(self.policy(), angwil)
        self.assertEqual(out[-1], zul)
        symbols = [self.wmap.rows[y][x] for y, x in out]
        self.assertEqual(len(out) - 1, 19)
        self.assertEqual(symbols.count("_"), 1)
        self.assertFalse(set(symbols) & {"~", "&", "$", "#"})
        back = self.walk(self.policy(returning=True), zul)
        self.assertEqual(back[-1], angwil)

    def test_eats_when_hungry(self):
        policy = self.policy()
        board = self.board(zul_trip.town_cell(self.wmap, ANGWIL))
        food = item("a", 80, 35, name="ration")
        hungry = replace(board, player=replace(board.player, food_state="hungry"), inventory=[food])
        key = policy.choose_key(hungry)
        self.assertEqual(policy.last_reason, zul_trip.EAT_REASON)
        self.assertTrue(key.startswith("E"), repr(key))

    def test_lost_levitation_falls_back_to_the_usual_return(self):
        policy = self.policy()
        key = policy.choose_key(self.board((20, 75), levitation=False))
        self.assertEqual(policy.last_reason, "wilderness:global-travel")
        self.assertFalse(zul_trip.trip_active(policy))
        self.assertIsNotNone(key)

    def test_without_a_trip_the_usual_return(self):
        policy = HengbotPolicy(wilderness_map=self.wmap)
        policy.choose_key(self.board((20, 75)))
        self.assertEqual(policy.last_reason, "wilderness:global-travel")


class AmbushTest(unittest.TestCase):
    """CONSTRUCTED local wilderness boards after an ambush (66x198)."""

    def board(self, position, monsters=(), messages=()):
        grids = {Position(y, x): grid(y, x)
                 for y in range(max(0, position.y - 3), position.y + 4)
                 for x in range(max(0, position.x - 3), position.x + 4)}
        return Snapshot(player(position.y, position.x, hp=400, max_hp=400, level=35),
                        grids, list(monsters), floor_key=(0, 0, 0), width=198, height=66,
                        town_flag=False, messages=list(messages))

    def policy(self):
        policy = HengbotPolicy()
        record = zul_trip.state(policy)
        record.active, record.start_town = True, ANGWIL
        return policy

    def test_an_awake_monster_is_not_fled(self):
        monster = hostile(1, 10, 12, hp=40, max_hp=40)
        policy = self.policy()
        policy.choose_key(self.board(Position(10, 10), [monster]))
        self.assertNotIn(policy.last_reason, {"wilderness:flee", zul_trip.EDGE_REASON,
                                              zul_trip.ENTER_GLOBAL_REASON})
        # Without the trip the usual survival flees it.
        usual = HengbotPolicy()
        usual.choose_key(self.board(Position(10, 10), [monster]))
        self.assertEqual(usual.last_reason, "wilderness:flee")

    def test_quiet_board_returns_to_the_global_map(self):
        policy = self.policy()
        self.assertEqual(policy.choose_key(self.board(Position(10, 10))), "<")
        self.assertEqual(policy.last_reason, zul_trip.ENTER_GLOBAL_REASON)

    def test_a_refused_global_map_walks_off_the_nearest_edge(self):
        policy = self.policy()
        refused = self.board(Position(3, 50), messages=[zul_trip.AMBUSH_MESSAGES[0]])
        self.assertIn(policy.choose_key(refused), {"7", "8", "9"})
        self.assertEqual(policy.last_reason, zul_trip.EDGE_REASON)
        at_edge = self.board(Position(1, 50))
        self.assertEqual(policy.choose_key(at_edge), "8")
        self.assertEqual(policy.last_reason, zul_trip.EDGE_REASON)


class ZulTowerTest(unittest.TestCase):
    """CONSTRUCTED Zul board beside building 14 (lib/edit/towns/05_Zul.jsonc)."""

    @classmethod
    def setUpClass(cls):
        cls.zul = parse_town_map(find_town_map(ZUL_TOWN_ID + 1, GAME))

    def board(self, gold, position=None):
        tower = self.zul.building_position(zul_trip.CHAOS_TOWER)
        here = position or next(Position(tower.y + dy, tower.x + dx)
                                for dy, dx in ((1, 0), (0, 1), (0, -1), (-1, 0), (1, 1))
                                if self.zul.is_walkable(Position(tower.y + dy, tower.x + dx)))
        grids = {}
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                cell = Position(here.y + dy, here.x + dx)
                if self.zul.is_walkable(cell):
                    grids[cell] = grid(cell.y, cell.x)
        for number, cell in self.zul.buildings.items():
            grids[cell] = GridState(position=cell, known=True, passable=True, wall=False,
                                    has_monster=False, has_down_stairs=False, has_up_stairs=False,
                                    unsafe=False, building_type=number)
        return Snapshot(
            player(here.y, here.x, hp=400, max_hp=400, level=35, gold=gold,
                   abilities=frozenset({"levitation"})),
            grids, [], floor_key=(0, 0, 0), width=self.zul.width, height=self.zul.height,
            town_flag=True, town_id=ZUL_TOWN_ID,
            equipment=[item("g", 39, 2, fuel=5000, is_equipment=True)])

    def policy(self, curable):
        policy = HengbotPolicy(town_map=self.zul, town_maps={ZUL_TOWN_ID: self.zul},
                               wilderness_map=wilderness())
        policy._mutation_signature = tuple(curable)
        record = zul_trip.state(policy)
        record.active, record.start_town = True, ANGWIL
        record.curable, record.price = tuple(curable), zul_trip.CURE_OTHER_PRICE
        return policy

    def test_cures_every_mutation_then_leaves_for_the_global_map(self):
        policy = self.policy((1, 3))
        board = self.board(20000)
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, zul_trip.CURE_REASON)
        self.assertRegex(key, r"^[1-9]mm\x1b$")
        # cmd-building.cpp: each 'm' takes the price and cures one.
        paid = replace(board, player=replace(board.player, gold=10000), turn=board.turn + 10)
        key = policy.choose_key(paid)
        self.assertEqual(zul_trip.state(policy).cured, 2)
        self.assertEqual((key, policy.last_reason), ("<", zul_trip.ENTER_GLOBAL_REASON))
        self.assertTrue(zul_trip.state(policy).returning)

    def test_short_gold_cures_what_it_pays_for(self):
        policy = self.policy((1, 3))
        key = policy.choose_key(self.board(7000))
        self.assertRegex(key, r"^[1-9]m\x1b$")

    def test_cure_entry_answers_only_the_building_menu(self):
        first, steps = compile_observed_input("2mm\x1b", ScreenKind.COMMAND, {}, zul_trip.CURE_REASON, [])
        self.assertEqual(first, "2")
        self.assertEqual([(set(step.kinds), step.keys, step.optional) for step in steps],
                         [({ScreenKind.BUILDING}, "m", True), ({ScreenKind.BUILDING}, "m", True),
                          ({ScreenKind.BUILDING}, "\x1b", True)])


if __name__ == "__main__":
    unittest.main()
