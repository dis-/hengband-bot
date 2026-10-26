"""Issue #47: recorded fare exhaustion and constructed transport controls.

Substrate: copied c4-a 08:38 (Morivant, 251G) and n1-b life-192
(Telmora, 5299 -> 449 -> 329G), plus its six supplier/quest travel decisions.
The extractor retains the raw rows and decision evidence. No running game
or recorder-owned files are read by tests.

DECLARED CONSTRUCTED: a fresh policy with current game definitions, empty
fresh Home knowledge and cached skill observation, in-store operations on.
The branch tests below explicitly describe changes to gold, pack, store,
and the admitted supplier circuit. They are counterfactuals, not replayed
post-fix game outcomes. UI controls use the production follow executor's
faithful hook harness; no send or decision implementation is mocked.
"""
import tests  # noqa: F401
import copy
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from dataclasses import replace
from tempfile import TemporaryDirectory

from hengbot.model import parse_snapshot, GridState, Position
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import TOWN_TELEPORT_COST, POLICY_FINAL_STOP_REASONS, RUMOR_COST, RUMOR_GOLD_RESERVE, RUMOR_READ_KEY, INN_BUILDING_TYPE
from hengbot.item_reservation import store_item_key
from hengbot.cli import _policy_final_stop_required
from tests import test_classA_observed_input as follow_harness
from tests.test_input_executor import ProductionHarness, command_screen, store_screen, prompt_screen
from tests.test_resume_inside_store import _fit
from hengbot.policy_types import CrossTownShoppingExpedition
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.town_maps import find_town_map, parse_town_map
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.quest_knowledge import load_quest_knowledge, find_quest_definitions
from hengbot.quest_strategies import load_quest_strategies

FIXTURE = Path(__file__).parent / "fixtures/broke-prevent-20261026.json.gz"
GAME = Path("C:/hengband")

class BrokePreventRecordedTest(ProductionHarness):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == "aa8a8f3a5ef8ba9c80e962d43ff56d60b5ccb35e1bf964d2df9b17b20b31decc"
        cls.capture = json.loads(gzip.decompress(FIXTURE.read_bytes()))
        cls.monrace = load_monrace_knowledge(GAME / "lib/edit/MonraceDefinitions.jsonc")
        cls.maps = {n - 1: parse_town_map(find_town_map(n, GAME)) for n in range(1, 6)}

    def raw(self, turn, *, gold=None, store=None, source="b"):
        return copy.deepcopy(next(r for r in self.capture[source]
            if r.get("turn") == turn and "player" in r
            and (gold is None or r["player"]["gold"] == gold)
            and ((r.get("store") or {}).get("store_type") == store)))

    def policy(self, raw):
        p = HengbotPolicy(
            town_map=self.maps[0], town_maps=self.maps,
            monrace_knowledge=self.monrace,
            dungeon_knowledge=load_dungeon_knowledge(GAME / "lib/edit/DungeonDefinitions.jsonc"),
            baseitem_costs=load_baseitem_costs(GAME / "lib/edit/BaseitemDefinitions.jsonc"),
            quest_knowledge=load_quest_knowledge(find_quest_definitions(GAME / "bot-client/state.jsonl")),
            quest_strategies=load_quest_strategies(Path(__file__).resolve().parents[1] / "strategy/quests"),
        )
        p._in_store_ops_enabled = True
        p._crossarea_fundraising_enforced = True
        board = parse_snapshot(raw, self.monrace)
        p.prime(board)
        p.consume_home_knowledge(())
        p._skill_exp_cache = (0, 0, board.player.level, p._town_visit_epoch)
        return p

    def decide(self, p, raw):
        board = parse_snapshot(raw, self.monrace)
        if board.store is not None:
            p.observe_store_screen(True)
        key = p.choose_key(board)
        if key:
            p.confirm_key_posted(key)
        return key, p.last_reason, board

    def follow(self, key, reason, raw, *, inside=False):
        # DECLARED CONSTRUCTED English store layout, drawn from the recorded
        # shelf with the game's label/name columns (display-store.cpp). Menu
        # and prompt classifiers reuse existing follow protocol controls.
        initial = None
        if inside:
            initial = store_screen()
            initial.update(height=80, lines=[""] * 80)
            initial["lines"][60] = "You may: p) Purchase an item. s) Sell an item."
            initial["lines"][61] = " ESC) Exit from Building."
            initial["cursor"]["y"] = 60
            for index, item in enumerate(raw["store"]["items"]):
                initial["lines"][6+index] = item["letter"] + ") " + _fit(item["name"],57)
        final = initial if inside and key != "\x1b" else command_screen()
        screens, states = [final], [copy.deepcopy(raw)]
        if reason == "shop:in-store-buy":
            screens = [
                follow_harness.recorded("live-screen-cap-05-alchemist-buy-p.json"),
                follow_harness.recorded("live-screen-cap-06-alchemist-buy-select-detection.json"),
                prompt_screen("Do you buy for $2425? [Y/n]"), initial,
            ]
            after = copy.deepcopy(raw)
            after["player"]["gold"] -= 2425
            bought = next(i for i in after["store"]["items"] if i["letter"] == "k")
            bought["count"] -= 1
            carried = {k:v for k,v in bought.items() if k not in ("letter","price")}
            carried.update(slot="u",count=1)
            after["inventory"].append(carried)
            states = [copy.deepcopy(raw) for _ in screens[:-1]] + [after]
        game, result = follow_harness.ClassAObservedInputPins.drive(
            self, key, reason, screens, initial=initial, raw=raw, states=states)
        self.assertEqual(result.outcome, "completed", result.reason)
        if reason == "shop:in-store-buy":
            self.assertGreaterEqual(result.board["player"]["gold"],TOWN_TELEPORT_COST)
            self.assertEqual(result.board["player"]["gold"],raw["player"]["gold"]-2425)
        return game.accepted

    def test_recorded_towns_and_spending_evidence(self):
        a = self.raw(2455721, gold=251, source="a")
        before = self.raw(2933932, gold=5299, store=4)
        after = self.raw(2933932, gold=449, store=4)
        broke = self.raw(2942109, gold=329)
        self.assertEqual([r["floor"]["town_id"] for r in (a,before,after,broke)],
                         [2,1,1,1])
        self.assertEqual(before["player"]["gold"] - after["player"]["gold"],
                         2 * next(i["price"] for i in before["store"]["items"]
                                  if i["letter"] == "k"))
        decisions = self.capture["decisions"]
        trips = [(r["reason"], r["key"]) for r in decisions
                 if r["key"] in ("3ma", "3mb", "3mc", "1mb", "3md")]
        self.assertEqual(trips, [
            ("town:cross-town-shopping:travel-0", "3ma"),
            ("fixedquest:q2-travel", "3mb"),
            ("town:cross-town-shopping:travel-2", "3mc"),
            ("fixedquest:q2-travel", "1mb"),
            ("town:cross-town-shopping:travel-3", "3md"),
            ("fixedquest:q2-travel", "1mb"),
        ])

    def test_public_buy_caps_two_identifies_at_the_return_fare_and_follow_posts_one(self):
        raw = self.raw(2933932, gold=5299, store=4)
        # DECLARED CONSTRUCTED: a second incomplete ego target represents the
        # captured two-scroll demand (the original process's Home queue is not
        # in this board). Keep the recorded shelf, gold, town and first target.
        extra = copy.deepcopy(next(i for i in raw["inventory"]
                                   if i["tval"] == 36))
        extra["slot"] = "t"
        raw["inventory"].append(extra)
        p = self.policy(raw)
        p._identification_need = "full"
        key, reason, board = self.decide(p, raw)
        self.assertEqual((key, reason), ("pk1\r\r", "shop:in-store-buy"))
        item = next(i for i in board.store.items if i.letter == "k")
        self.assertGreaterEqual(board.player.gold - item.price, TOWN_TELEPORT_COST)
        self.assertLess(board.player.gold - 2 * item.price, TOWN_TELEPORT_COST)
        self.assertEqual(self.follow(key, reason, raw, inside=True), ["p","k","1\r","\r"])

    def test_common_purchase_composer_refuses_stale_overbudget_quantity(self):
        raw = self.raw(2933932, gold=5299, store=4)
        p = self.policy(raw)
        board = parse_snapshot(raw, self.monrace)
        item = next(i for i in board.store.items if i.letter == "k")
        self.assertIsNone(store_item_key(p, board, "buy", item, "shop-buy", quantity=2))
        self.assertIsNone(store_item_key(p, board, "buy", item, "shop-buy", quantity=0))
        self.assertIsNotNone(store_item_key(p, board, "buy", item, "shop-buy", quantity=1))

    def test_public_exact_fare_store_keeps_every_gold_and_leaves(self):
        raw = self.raw(2933932,gold=5299,store=4)
        raw["player"]["gold"] = TOWN_TELEPORT_COST
        p = self.policy(raw)
        p._identification_need = "full"
        key,reason,_ = self.decide(p,raw)
        self.assertEqual((key,reason),("\x1b","shop:observe-and-leave"))
        self.assertEqual(self.follow(key,reason,raw,inside=True),[key])

    def test_partial_wand_price_uncertainty_cannot_use_reserved_fare(self):
        # DECLARED CONSTRUCTED charge-rounding control on the captured shelf:
        # partial wand copies may cost more than the exported per-unit price.
        raw = self.raw(2933932,gold=5299,store=4)
        raw["player"]["gold"] = TOWN_TELEPORT_COST + 2425
        raw["store"]["items"] = [{**raw["store"]["items"][10],
                                     "tval":65,"sval":15,"count":2}]
        p = self.policy(raw)
        board = parse_snapshot(raw,self.monrace)
        item = board.store.items[0]
        self.assertEqual(p._purchase_quantity(board,item),0)
        self.assertIsNone(store_item_key(p,board,"buy",item,"shop-buy",quantity=1))
        # The whole stack has the same charges as the exported price source.
        raw["player"]["gold"] = TOWN_TELEPORT_COST + 2*item.price
        board = parse_snapshot(raw,self.monrace)
        self.assertIsNotNone(store_item_key(p,board,"buy",board.store.items[0],
                                          "shop-buy",quantity=2))

    def rumor(self, gold):
        # DECLARED CONSTRUCTED paid-action control. Use A's town/pack with
        # an adjacent building matching the rumor producer's INN predicate.
        # This checks the producer's budget, not a recorded Morivant rumor UI.
        raw = self.raw(2455721,gold=251,source="a")
        raw["player"].update(gold=gold,y=10,x=10)
        raw["progress"]["visited_town_ids"] = [0,2]
        p = self.policy(raw)
        board = parse_snapshot(raw,self.monrace)
        def cell(x,building=-1):
            return GridState(Position(10,x),True,True,False,False,False,False,False,
                             building_type=building)
        board = replace(board,grids={Position(10,10):cell(10),
                                     Position(10,11):cell(11,INN_BUILDING_TYPE)})
        p._build_grid_index(board)
        p._town_travel_rumor_pending = 1
        key = p._town_special_key(board)
        return key,p.last_reason

    def test_paid_rumor_requires_fare_plus_one_read(self):
        for gold in (TOWN_TELEPORT_COST,TOWN_TELEPORT_COST+RUMOR_COST-1):
            key,reason = self.rumor(gold)
            self.assertEqual(reason,"town:rumor-needs-funds")
            self.assertNotIn(RUMOR_READ_KEY,key)

    def test_paid_rumor_batch_cannot_consume_return_fare(self):
        gold = TOWN_TELEPORT_COST + 2*RUMOR_COST
        key,reason = self.rumor(gold)
        self.assertEqual((key,reason),("6"+RUMOR_READ_KEY*2+"\x1b","town:rumor-batch"))
        self.assertEqual(gold-key.count(RUMOR_READ_KEY)*RUMOR_COST,TOWN_TELEPORT_COST)

    def test_public_paid_rumor_preserves_town_reserve_and_follow_posts_batch(self):
        # DECLARED CONSTRUCTED: A's pack beside an inn, with a pending travel
        # rumor and just two reads above the reserve. At the Outpost the
        # older, lower rumor reserve applies instead of the return fare.
        for town, reserve in ((2, TOWN_TELEPORT_COST), (0, RUMOR_GOLD_RESERVE)):
            with self.subTest(town=town):
                gold = reserve + 2 * RUMOR_COST
                raw = self.raw(2455721, gold=251, source="a")
                raw["floor"].update(town_id=town, town_index=town + 1)
                raw["player"].update(gold=gold, y=10, x=10)
                raw["progress"]["visited_town_ids"] = [0, 2]
                raw.pop("grid_map", None)
                raw["nearby_grids"] = [
                    {"y":10, "x":x, "known":True, "terrain":{"move":True},
                     "building_type":building}
                    for x, building in ((10, -1), (11, INN_BUILDING_TYPE))
                ]
                p = self.policy(raw)
                p._town_travel_rumor_pending = 1
                self.empty_suppliers(p, raw)
                key, reason, _ = self.decide(p, raw)
                reads = (gold - reserve) // RUMOR_COST
                self.assertEqual((key, reason),
                                 ("6" + RUMOR_READ_KEY * reads + "\x1b", "town:rumor-batch"))
                self.assertEqual(gold - key.count(RUMOR_READ_KEY) * RUMOR_COST, reserve)
                self.assertEqual(self.follow(key, reason, raw), [key])

    def test_outpost_has_no_return_fare_purchase_reserve(self):
        raw = self.raw(2933932, gold=5299, store=4)
        raw["floor"].update(town_id=0, town_index=1)
        p = self.policy(raw)
        board = parse_snapshot(raw, self.monrace)
        item = next(i for i in board.store.items if i.letter == "k")
        self.assertIsNotNone(store_item_key(p, board, "buy", item, "shop-buy", quantity=2))

    def test_recorded_broke_boards_stop_without_sellable_surplus(self):
        for turn, gold, source in ((2455721,251,"a"),(2942109,329,"b")):
            with self.subTest(source=source):
                raw = self.raw(turn, gold=gold, source=source)
                # Round 2: the original supplies now fund the fare. This
                # no-sale control keeps only their existing return minima.
                for item in raw["inventory"]:
                    if (item["tval"], item["sval"]) == (70, 9):
                        item["count"] = 4
                    elif (item["tval"], item["sval"]) == (75, 36):
                        item["count"] = 2
                p = self.policy(raw)
                p._fundraising_mode = "mine"  # captured mining set
                key, reason, _ = self.decide(p, raw)
                self.assertEqual(reason, "town:blocked:outpost-fare-no-sale")
                self.assertTrue(_policy_final_stop_required(p))
                self.assertNotIn("r", key or "")
                self.assertEqual(self.decide(p, raw)[1], reason)

    def _with_surplus_book(self):
        raw = self.raw(2942109, gold=329)
        # DECLARED CONSTRUCTED unneeded known third realm book, using the
        # ordinary valuable-book sale authority; all recorded supplies stay.
        book = copy.deepcopy(raw["inventory"][-1])
        book.update(slot="q", tval=90, sval=2, count=1, name="Life Book 3",
                    inscription="", is_equipment=False, fully_known=True,
                    known_flags=[])
        raw["inventory"].append(book)
        return raw

    def test_public_broke_sale_then_return_uses_follow_and_preserves_recall(self):
        for enforced in (False, True):
            with self.subTest(claim_bar=enforced):
                raw = self._with_surplus_book()
                original_recall = copy.deepcopy(next(i for i in raw["inventory"]
                                                     if (i["tval"],i["sval"]) == (70,11)))
                p = self.policy(raw)
                p._town_claim_bar_enforced = enforced
                key, reason, _ = self.decide(p, raw)
                self.assertEqual(reason, "shop:outpost-fare-sale-approach")
                self.assertTrue(key)
                # DECLARED CONSTRUCTED arrival at the chosen Temple.
                page = copy.deepcopy(raw)
                page["store"] = {"store_type":3, "items":[], "stock_num":0,
                                 "page_top":0, "page_size":52}
                key, reason, _ = self.decide(p, page)
                self.assertEqual((key,reason), ("{q@1\r", "shop:batch-inscribe"))
                # The game observes the chosen inscription before the sale.
                page["inventory"][-1]["inscription"] = "@1"
                key, reason, _ = self.decide(p, page)
                self.assertEqual((key,reason), ("d1y", "shop:one-shot-sale-compose"))
                self.assertEqual(self.follow(key,reason,page,inside=True), [key])
                # DECLARED CONSTRUCTED confirmed sale earns exactly the fare;
                # observe the pending transaction before selecting the return.
                page["inventory"].pop()
                page["player"]["gold"] = TOWN_TELEPORT_COST
                key, reason, _ = self.decide(p, page)
                self.assertEqual((key,reason), ("\x1b", "shop:one-shot-sale-observed"))
                self.assertIsNone(p._batch_sell_pending)
                self.assertEqual(self.follow(key,reason,page,inside=True), [key])
                outside = copy.deepcopy(page)
                outside.pop("store")
                outside["player"].update(y=27,x=55)  # recorded Telmora inn approach
                key, reason, _ = self.decide(p, outside)
                self.assertEqual((key,reason), ("3ma", "town:cross-town-outpost-fare-return"))
                self.assertEqual(self.follow(key,reason,outside), [key])
                self.assertEqual(next(i for i in outside["inventory"]
                                      if (i["tval"],i["sval"]) == (70,11)), original_recall)
                self.assertTrue(p._outpost_fare_recovering)
                # DECLARED CONSTRUCTED Outpost arrival ends recovery.
                outside["floor"].update(town_id=0,town_index=1)
                outside["player"]["gold"] = 0
                self.decide(p, outside)
                self.assertFalse(p._outpost_fare_recovering)

    def test_unproductive_sale_closes_once_and_does_not_reinscribe_forever(self):
        raw = self._with_surplus_book()
        p = self.policy(raw)
        self.decide(p,raw)
        raw["player"].update(y=p._shopping_approach_goal.y,
                             x=p._shopping_approach_goal.x)
        raw["store"] = {"store_type":3,"items":[],"stock_num":0,
                        "page_top":0,"page_size":52}
        self.assertEqual(self.decide(p,raw)[0],"{q@1\r")
        raw["inventory"][-1]["inscription"] = "@1"
        self.assertEqual(self.decide(p,raw)[0],"d1y")
        # DECLARED CONSTRUCTED refused sale: no gold or pack effect.
        self.assertEqual(self.decide(p,raw)[0],"\x1b")
        self.assertIn(3,p._store_sale_refused)
        raw.pop("store")
        # Round 2 can still try reserved supplies at the Alchemist. Refusing
        # that shop as well constructs exhaustion of both sale steps.
        p._store_sale_refused.update((4, 5))
        for _ in range(3):
            self.assertEqual(self.decide(p,raw)[1],"town:blocked:outpost-fare-no-sale")

    def test_broke_store_page_leaves_without_buying_mining_kit(self):
        raw = self.raw(2940687,gold=449,store=4)
        # Round 2 admits a reserved sale here, so use the existing minimum
        # quantities for this leave-without-buying control.
        for item in raw["inventory"]:
            if (item["tval"], item["sval"]) == (70, 9):
                item["count"] = 4
            elif (item["tval"], item["sval"]) == (75, 36):
                item["count"] = 2
        p = self.policy(raw)
        p._fundraising_mode = "mine"
        key, reason, _ = self.decide(p, raw)
        self.assertEqual((key,reason), ("\x1b","shop:outpost-fare-seek-sale-leave"))
        self.assertEqual(self.follow(key,reason,raw,inside=True), [key])

    def test_recovery_names_active_recall_stop_without_cancel_read(self):
        raw = self.raw(2941543,gold=329)
        self.assertTrue(raw["player"]["recalling"])
        p = self.policy(raw)
        key, reason, _ = self.decide(p, raw)
        self.assertEqual(reason,"town:blocked:outpost-fare-recall-active")
        self.assertTrue(_policy_final_stop_required(p))
        self.assertNotIn("r", key or "")

    def trip(self, town=0, gold=7014):
        # DECLARED CONSTRUCTED counterfactual across the missing raw-board
        # window: keep B's pack/quest state, remove Teleport to create a stable
        # supply shortfall and mark local shelves empty. The circuit and inn
        # coordinates come from its captured travel decisions. No selector or
        # route method is stubbed.
        raw = self.raw(2933932,gold=5299,store=4)
        raw.pop("store")
        raw["inventory"] = [i for i in raw["inventory"] if (i["tval"],i["sval"]) != (70,9)]
        positions = {0:(36,118),2:(42,93),3:(14,89)}
        y,x = positions[town]
        raw["floor"].update(town_id=town,town_index=town+1)
        raw["player"].update(y=y,x=x,gold=gold)
        raw["grid_map"] = {"palette":[],"runs":[]}
        p = self.policy(raw)
        p._cross_town_shopping = CrossTownShoppingExpedition(
            1,("teleport",),{"teleport":904},1000,2404,(0,2,3),[0])
        self.empty_suppliers(p, raw)
        return p, raw

    def empty_suppliers(self, p, raw):
        board = parse_snapshot(raw,self.monrace)
        for store in range(8):
            p._town_store_attempted[store] = board.turn
        for store in p._cross_town_supplier_types(board,"teleport"):
            p._town_visit_ledger.shelf_observations[(store,"teleport")] = ()

    def test_public_supplier_circuit_preempts_q2_between_empty_towns(self):
        p,raw = self.trip()
        key, reason, board = self.decide(p,raw)
        self.assertEqual((key,reason),("3mc","town:cross-town-shopping:travel-2"))
        self.assertEqual(self.follow(key,reason,raw),[key])
        # DECLARED CONSTRUCTED paid arrival in Morivant, then exhausted local
        # shelves. Arrival closes the travel child and preserves the circuit.
        raw["floor"].update(town_id=2,town_index=3)
        raw["player"].update(y=42,x=93,gold=raw["player"]["gold"]-TOWN_TELEPORT_COST)
        self.decide(p,raw)  # arrival observes new town, local owners may inspect
        self.empty_suppliers(p,raw)
        key, reason, _ = self.decide(p,raw)
        self.assertEqual((key,reason),("1md","town:cross-town-shopping:travel-3"))
        self.assertEqual(self.follow(key,reason,raw),[key])
        self.assertEqual(p._cross_town_shopping.tried_towns,[0,2])

    def test_supplier_circuit_has_named_exhaustion_and_no_second_tour(self):
        p,raw = self.trip(town=3)
        p._cross_town_shopping.tried_towns[:] = [0,2,3]
        board = parse_snapshot(raw,self.monrace)
        self.assertIsNone(p._cross_town_shopping_key(board))
        self.assertEqual(p._decision_offer_buffer().no_steps[-1][2],
                         "candidate-towns-exhausted")
        for _ in range(3):
            key,reason,_ = self.decide(p,raw)
            self.assertFalse(reason.startswith("town:cross-town-shopping:travel-"))
            self.assertEqual(p._cross_town_shopping.tried_towns,[0,2,3])

    def test_local_shopping_hold_does_not_deadlock_the_next_supplier(self):
        p,raw = self.trip()
        board = parse_snapshot(raw,self.monrace)
        self.assertFalse(p._cross_town_shopping_hold(board))
        self.assertTrue(p._cross_town_quest_hold(board))
        p._cross_town_shopping.tried_towns[:] = [0,2,3]
        self.assertFalse(p._cross_town_quest_hold(board))

    def test_trip_fare_boundary_preserves_the_outpost_return(self):
        for gold in (2*TOWN_TELEPORT_COST-1,2*TOWN_TELEPORT_COST):
            p,raw = self.trip(gold=gold)
            key,reason,_ = self.decide(p,raw)
            if gold >= 2*TOWN_TELEPORT_COST:
                self.assertEqual((key,reason),("3mc","town:cross-town-shopping:travel-2"))
                self.assertEqual(self.follow(key,reason,raw),[key])
                self.assertGreaterEqual(gold-TOWN_TELEPORT_COST,TOWN_TELEPORT_COST)
            else:
                self.assertNotIn(key,("3mc","3mb"))
                self.assertIsNone(p._cross_town_shopping.target_town_id)
                self.assertEqual(p._cross_town_shopping.tried_towns,[0,2,3])

if __name__ == "__main__":
    unittest.main()
