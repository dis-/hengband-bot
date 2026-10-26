"""Issue #47: captured income/town boards and constructed store replies.

The fixture contains selected observations, source quest facts and provenance;
all inventory/count/price counterfactuals below are declared constructed.
"""
import tests  # noqa: F401
import copy
import gzip
import io
import json
import time
import pickle
from dataclasses import replace
from pathlib import Path
import unittest

from hengbot.model import *
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import QUEST_STATUS_COMPLETED, QUEST_STATUS_TAKEN
from hengbot.quest_knowledge import QuestInfo, QuestBattlefield
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.quest_strategies import load_quest_strategies
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_decision_key_with_prompt_chain
from tests.test_input_executor import ProductionHarness, FaithfulHookGame, command_screen, prompt_screen, store_screen
from tests.policy_fixtures import grid, item, store_item

FIXTURE = Path(__file__).with_name("fixtures") / "opening-route-20261026.json.gz"


def captured():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def make_policy(data):
    quests = {}
    for key, values in data["quests"].items():
        facts = copy.deepcopy(values)
        terrain = facts.pop("battlefield")
        terrain["terrain"] = {(y, x): value for y, x, value in terrain["terrain"]}
        for name in ("entrance", "exit", "player_start", "reward_tile"):
            if terrain.get(name) is not None:
                terrain[name] = tuple(terrain[name])
        for name in ("searchable", "chokepoints"):
            terrain[name] = tuple(map(tuple, terrain[name]))
        terrain["monster_placements"] = tuple((tuple(pos), race) for pos, race in terrain["monster_placements"])
        facts["placed_monsters"] = tuple(map(tuple, facts["placed_monsters"]))
        facts["battlefield"] = QuestBattlefield(**terrain)
        quests[int(key)] = QuestInfo(**facts)
    races = {}
    for key, values in data["monraces"].items():
        values = dict(values)
        for name in ("flags", "abilities"):
            values[name] = frozenset(values[name])
        values["blows"] = tuple(MonsterBlow(**blow) for blow in values["blows"])
        races[int(key)] = MonraceKnowledge(**values)
    policy = HengbotPolicy(quest_knowledge=quests, monrace_knowledge=races,
                         quest_strategies=load_quest_strategies(Path("strategy/quests")))
    policy.consume_skill_knowledge(data["skill"])
    return policy


class OpeningRouteRecordedTest(ProductionHarness):
    @classmethod
    def setUpClass(cls):
        cls.data = captured()

    def policy(self):
        return make_policy(self.data)

    def prepare(self, policy, board):
        policy.prime(board)
        knowledge = copy.deepcopy(self.data["skill"])
        # DECLARED CONSTRUCTED: the same skill-exp reply at this seed's CL.
        knowledge["player"]["level"] = board.player.level
        policy.consume_skill_knowledge(knowledge)

    def seed(self, tag):
        return parse_snapshot(copy.deepcopy(self.data["seeds"][tag]["snapshot"]), self.policy()._monrace_knowledge)

    def test_income_combat_keeps_the_last_q1_torches(self):
        # DECLARED CONSTRUCTED: keep only the mandatory five from the captured
        # ten-torch inventory; an ordinary target still stands on the same ray.
        policy = self.policy()
        board = self.seed("throw")
        torches = [it for it in board.inventory if it.is_torch]
        board = replace(board, inventory=tuple(it for it in board.inventory if not it.is_torch)
                        + (replace(torches[0], count=5),))
        self.prepare(policy, board)
        policy._fundraising_mode = "mine"
        key = policy.choose_key(board)
        self.assertNotEqual(policy.last_reason, "ranged:throw-torch", key)
        self.assertEqual(policy._count_throwing_torches(board), 5)
        self.assertGreaterEqual(sum(policy._retention_reservation(board, it)
                                   for it in board.inventory if it.is_torch), 5)

    def test_observed_general_page_rebuys_q1_torches(self):
        policy = self.policy()
        town = self.seed("oil")
        general = self.seed("general")
        # DECLARED CONSTRUCTED: knowledge of the reachable kit suppliers is
        # complete, preserving the copied General Store offers and character.
        board = replace(town, store=general.store)
        self.prepare(policy, board)
        policy._in_store_ops_enabled = True
        policy._fundraising_mode = "mine"
        policy._equipment_optimization_last_depth = 20
        policy.observe_store_screen(True)
        for store in (STORE_GENERAL, STORE_WEAPON, STORE_BLACK, STORE_ALCHEMIST):
            policy._town_supplier_stock[store] = (general.store if store == STORE_GENERAL else StoreState(store, []))
            policy._town_supplier_stock_observations[store] = (0, board.turn)
        key = policy.choose_key(board)
        self.assertIsNotNone(key)
        self.assertIn(policy.last_reason, {"shop:buy-torch", "shop:in-store-buy"})
        selected = policy._next_purchase(board)
        self.assertTrue(selected.is_torch, selected)
        self.assertEqual(policy._purchase_quantity(board, selected), 5)

    @staticmethod
    def shelf_screen(raw):
        screen = store_screen()
        for index, it in enumerate(raw["store"]["items"]):
            screen["lines"][6 + index] = f"{it['letter']}) {it['name']}"
        store = raw["store"]
        if store.get("stock_num", 0) > store.get("page_size", 99):
            number = store["page_top"] // store["page_size"] + 1
            screen["lines"][5] = " " * 20 + f"(Page {number})"
        return screen

    def post(self, policy, raw, key, following):
        """Constructed game replies, production follow sender and prompt gates."""
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.jsonl = [copy.deepcopy(raw)]
        game.screen = self.shelf_screen(raw) if raw.get("store") else command_screen(raw["turn"])
        screens = []
        expected = [key]
        if policy.last_reason == "shop:in-store-buy":
            letter = key[1]
            row = next(it for it in raw["store"]["items"] if it["letter"] == letter)
            quantity = int(key[2:].strip() or 1)
            screens = [prompt_screen("(Items a-z, ESC to exit) Which item?")]
            expected = ["p", letter]
            if row["count"] > 1:
                screens.append(prompt_screen(f"\u3044\u304f\u3064\u3067\u3059\u304b (1-{row['count']}): 1"))
                expected.append(f"{quantity}\r")
            screens.append(prompt_screen(f"Do you buy for ${row['price'] * quantity}? [Y/n]"))
            expected.append("\r")
        if policy.last_reason == "quest:enter":
            screens = [prompt_screen("Do you enter? [y/n]")]
            expected = [key, "y"]
        game.screens = screens + [self.shelf_screen(following) if following.get("store")
                                  else command_screen(following["turn"])]
        game.states = [copy.deepcopy(raw) for _ in screens] + [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, "opening-route-replay", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 10,
            poll_interval=0, prompt_japanese=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(raw, policy._monrace_knowledge),
            posting_contract=PostingContract(), in_store=bool(raw.get("store")))
        self.assertTrue(sent, getattr(port.last_result, "reason", None))
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(game.accepted, expected)
        self.assertFalse(game.term_fifo)
        policy.confirm_key_posted(key)

    def shopping_case(self, *, gold=500, hp=250, carry=False):
        # DECLARED CONSTRUCTED: copied Lv10 board and General Store, with a
        # closed supplier census, controlled digging offers, detection price, and HP=250 to satisfy
        # the independent existing three-turn threat gate.
        raw = copy.deepcopy(self.data["seeds"]["oil"]["snapshot"])
        general = copy.deepcopy(self.data["seeds"]["general"]["snapshot"]["store"])
        torch = next(it for it in general["items"] if it["tval"] == TVAL_LITE and it["sval"] == SV_LITE_TORCH)
        torch["letter"] = "a"
        digger = next(it for it in general["items"] if it["tval"] == TVAL_DIGGING)
        digger.update(letter="b", price=450, count=1, pval=3)
        dear = dict(digger, letter="c", price=490, pval=4)
        general["items"] = [torch, digger, dear]
        general["stock_num"] = len(general["items"])
        detection = copy.deepcopy(next(it for it in raw["inventory"] if it["tval"] == TVAL_SCROLL and it["sval"] == SV_SCROLL_DETECT_TREASURE))
        detection.pop("slot")
        detection.update(letter="a", price=10, count=99)
        alchemist = dict(general, store_type=STORE_ALCHEMIST, items=[detection], stock_num=1)
        raw["inventory"] = [it for it in raw["inventory"] if it["tval"] != TVAL_DIGGING and not (it["tval"] == TVAL_SCROLL and it["sval"] == SV_SCROLL_DETECT_TREASURE)]
        if not carry:
            raw["inventory"] = [it for it in raw["inventory"] if it["tval"] != TVAL_POTION]
        raw["player"]["gold"] = gold
        if hp is not None:
            raw["player"]["hp"] = raw["player"]["max_hp"] = hp
        raw["store"] = general
        policy = self.policy()
        self.prepare(policy, parse_snapshot(raw, policy._monrace_knowledge))
        policy._in_store_ops_enabled = True
        for store, page in ((STORE_GENERAL, general), (STORE_ALCHEMIST, alchemist),
                            (STORE_WEAPON, dict(general, store_type=STORE_WEAPON, items=[], stock_num=0)),
                            (STORE_BLACK, dict(general, store_type=STORE_BLACK, items=[], stock_num=0))):
            policy._town_supplier_stock[store] = parse_snapshot(dict(raw, store=page), policy._monrace_knowledge).store
            policy._town_supplier_stock_observations[store] = (0, raw["turn"])
        return policy, raw, alchemist

    def buy_reply(self, raw, key):
        following = copy.deepcopy(raw)
        row = next(it for it in following["store"]["items"] if it["letter"] == key[1])
        quantity = int(key[2:].strip() or 1)
        following["player"]["gold"] -= row["price"] * quantity
        pack = copy.deepcopy(row)
        pack.pop("price"); pack.pop("letter")
        pack["count"] = quantity
        slots = {it["slot"] for it in following["inventory"]}
        pack["slot"] = next(slot for slot in "abcdefghijklmnopqrstuvw" if slot not in slots)
        following["inventory"].append(pack)
        row["count"] -= quantity
        removed = sum(it["count"] == 0 for it in following["store"]["items"])
        following["store"]["items"] = [it for it in following["store"]["items"] if it["count"]]
        following["store"]["stock_num"] -= removed
        for index, it in enumerate(following["store"]["items"]):
            it["letter"] = chr(ord("a") + index)
        following["turn"] += 1
        return following

    def test_fixed_route_buys_affordable_best_kit_and_posts_q1_request(self):
        policy, raw, alchemist = self.shopping_case()
        transactions = []
        for expected in ("a", "b"):
            board = parse_snapshot(raw, policy._monrace_knowledge)
            policy.observe_store_screen(True)
            key = str(policy.choose_key(board))
            self.assertEqual(key[0:2], "p" + expected, policy.last_reason)
            following = self.buy_reply(raw, key)
            self.post(policy, raw, key, following)
            transactions.append((expected, raw["player"]["gold"] - following["player"]["gold"]))
            raw = following
        # Observe and post the real exit, settling the previous buy before
        # the constructed travel reply opens the next supplier.
        key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
        self.assertEqual(key, "\x1b", policy.last_reason)
        outside = copy.deepcopy(raw)
        outside["store"] = None
        outside["turn"] += 1
        self.post(policy, raw, key, outside)
        raw = outside
        # DECLARED CONSTRUCTED: execute the selected approach to Alchemist.
        approach = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
        arriving = copy.deepcopy(raw)
        arriving["store"] = alchemist
        arriving["turn"] += 1
        policy.confirm_key_posted(approach)
        raw = arriving
        policy.observe_store_screen(True)
        key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
        self.assertEqual(key, "pa3\r\r", policy.last_reason)
        following = self.buy_reply(raw, key)
        self.post(policy, raw, key, following)
        raw = following
        self.assertEqual(transactions, [("a", 15), ("b", 450)])
        self.assertEqual(raw["player"]["gold"], 5)
        # DECLARED CONSTRUCTED: outside Q1's entrance after shopping. This
        # isolates acceptance from the uninteresting town walking distance.
        key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
        self.assertEqual(key, "\x1b", policy.last_reason)
        outside = copy.deepcopy(raw)
        outside["store"] = None
        outside["turn"] += 1
        self.post(policy, raw, key, outside)
        raw = outside
        raw["player"]["y"], raw["player"]["x"] = 27, 98
        key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
        self.assertEqual(policy.last_reason, "fixedquest:request", (key, getattr(policy, "_opening_q1_failure", None)))
        self.assertEqual(key, "8q\x1b")
        accepted = copy.deepcopy(raw)
        accepted["progress"]["quests"].append(dict(id=1, status=QUEST_STATUS_TAKEN, fixed=True, level=5, type=6, name="Q1"))
        accepted["player"]["y"] -= 1
        accepted["turn"] += 1
        self.post(policy, raw, key, accepted)
        self.assertTrue(policy._opening_q1_kit_bought)
        self.assertEqual(policy._count_throwing_torches(parse_snapshot(accepted, {})), 5)
        # The actual request response opens Q1's public town entrance.
        # DECLARED CONSTRUCTED: acceptance changes the building into the
        # public quest entrance, as emitted on the next town observation.
        from hengbot.model import _GRID_TERRAIN_NAMES
        cell = next(cell for cell in accepted["grid_map"]["cells"] if cell.get("p") == 1)
        cell["q"] = 1
        palette = accepted["grid_map"]["palette"]
        base = next(run[3] for run in accepted["grid_map"]["runs"]
                    if run[0] == cell["y"] and run[1] <= cell["x"] < run[1] + run[2])
        terrain = list(palette[base])
        terrain[2] |= 1 << _GRID_TERRAIN_NAMES.index("quest_enter")
        palette.append(terrain)
        accepted["grid_map"]["runs"].append([cell["y"], cell["x"], 1, len(palette) - 1])
        board = parse_snapshot(accepted, policy._monrace_knowledge)
        positions = policy._fixed_quest_entrance_positions(board, 1)
        self.assertTrue(positions)
        pos = min(positions)
        accepted["player"]["y"], accepted["player"]["x"] = pos.y, pos.x
        policy = pickle.loads(pickle.dumps(policy))
        key = str(policy.choose_key(parse_snapshot(accepted, policy._monrace_knowledge)))
        self.assertEqual((key, policy.last_reason), (">", "quest:enter"))
        # DECLARED CONSTRUCTED: the entry reply proves the floor change; combat
        # itself remains the existing approved Q1 navigator/strategy.
        inside = copy.deepcopy(accepted)
        inside["floor"].update(in_town=False, quest_id=1, level=5)
        inside["turn"] += 1
        self.post(policy, accepted, key, inside)

    def test_no_digger_and_other_readiness_refusals_stop_by_name(self):
        policy, raw, _ = self.shopping_case()
        raw["store"] = None
        for st, page in list(policy._town_supplier_stock.items()):
            items = [it for it in page.items if not it.is_digging_tool]
            policy._town_supplier_stock[st] = replace(page, items=items, stock_num=len(items))
        # DECLARED CONSTRUCTED: supplies already owned, no digger at any shelf.
        torch = self.data["seeds"]["general"]["snapshot"]["store"]["items"][8]
        torch = dict(torch, slot="t", count=5)
        raw["inventory"].append(torch)
        key = policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge))
        self.assertEqual(policy.last_reason, "quest:blocked:opening-route", key)
        self.assertEqual(policy._opening_q1_failure, "stop:no-digger")
        self.assertIn(policy.last_reason, __import__('hengbot.policy_constants', fromlist=['POLICY_FINAL_STOP_REASONS']).POLICY_FINAL_STOP_REASONS)
        from hengbot.cli import _policy_final_stop_banner
        self.assertIn("Q34", _policy_final_stop_banner(policy.last_reason))

    def test_reserved_potions_and_torches_cannot_be_sold_or_deposited(self):
        policy, raw, _ = self.shopping_case(hp=80)
        torch = dict(raw["store"]["items"][0], slot="t", count=5)
        raw["inventory"].append(torch)
        for slot, sval, count in (("u", SV_POTION_HEALING, 2), ("v", SV_POTION_SPEED, 1)):
            raw["inventory"].append(dict(slot=slot, name="reserved", tval=TVAL_POTION, sval=sval,
                                         count=count, known=True, aware=True, charging=False))
        board = parse_snapshot(raw, policy._monrace_knowledge)
        for it in board.inventory:
            if it.slot in {"t", "u", "v"}:
                self.assertEqual(policy._retention_surplus(board, it), 0, it)
        self.assertEqual([r[1] for r in policy._opening_q1_requirements(board)], [5, 2, 1])

    def test_non_torch_readiness_failure_stops_without_an_unrelated_departure(self):
        policy, raw, _ = self.shopping_case(hp=219)
        raw["store"] = None
        raw["inventory"].append(dict(self.data["seeds"]["general"]["snapshot"]["store"]["items"][8], slot="t", count=5))
        # DECLARED CONSTRUCTED: kit already acquired by this opening transaction.
        policy._opening_q1_kit_bought = True
        key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
        self.assertEqual((key, policy.last_reason), ("", "quest:blocked:opening-route"))
        self.assertIn("three-turn-threat", policy._opening_q1_failure)
        repeated = policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge))
        self.assertEqual(str(repeated), "")

    def test_missing_reserve_opens_only_a_bounded_income_run_and_returns(self):
        policy, raw, _ = self.shopping_case(gold=0)
        raw["store"] = None
        key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
        self.assertIn(policy.last_reason, {"town:travel-entrance", "opening-q1:fundraising-approach"}, key)
        self.assertEqual(policy._opening_q1_funding, 0)
        self.assertEqual(policy._fundraising_gold_target(), 15)
        self.assertEqual(policy._planned_mining_runs, 1)
        self.assertEqual(policy._fundraising_mode, "scavenge")
        policy.confirm_key_posted(key)
        # DECLARED CONSTRUCTED: the income run's calm upstairs observation,
        # earned gold, then its town arrival. Only transport is synthesized.
        outside = copy.deepcopy(self.data["seeds"]["throw"]["snapshot"])
        outside["visible_monsters"] = []
        outside["detected_monsters"] = []
        outside["player"]["gold"] = 600
        outside["player"]["hp"] = outside["player"]["max_hp"]
        policy.prime(parse_snapshot(outside, policy._monrace_knowledge))
        knowledge = copy.deepcopy(self.data["skill"])
        knowledge["player"]["level"] = outside["player"]["level"]
        policy.consume_skill_knowledge(knowledge)
        key = str(policy.choose_key(parse_snapshot(outside, policy._monrace_knowledge)))
        self.assertTrue(policy._opening_q1_funding_left, (key, policy.last_reason))
        raw["turn"] = outside["turn"] + 1
        raw["player"]["gold"] = 600
        self.prepare(policy, parse_snapshot(raw, policy._monrace_knowledge))
        key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
        self.assertIsNone(policy._opening_q1_funding)
        self.assertIsNone(policy._fundraising_mode)
        self.assertIn(policy.last_reason, {"shop:travel", "shop:travel:await-entry", "shop:one-shot-buy", "shop:approach"}, key)

    def test_funding_without_income_or_sellable_loot_stops(self):
        policy, raw, _ = self.shopping_case(gold=0)
        raw["store"] = None
        # DECLARED CONSTRUCTED: completed income transport with no proceeds.
        policy._opening_q1_funding = 0
        policy._opening_q1_funding_left = True
        key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
        self.assertEqual((key, policy.last_reason), ("", "quest:blocked:opening-route"))
        self.assertEqual(policy._opening_q1_failure, "stop:fundraising-no-income")

    def test_q1_kit_is_retained_even_with_normal_fundraising_mode_cleared(self):
        policy, raw, _ = self.shopping_case()
        source = self.data["seeds"]["oil"]["snapshot"]["inventory"]
        raw["inventory"].extend(copy.deepcopy(it) for it in source if it["tval"] == TVAL_DIGGING or (it["tval"] == TVAL_SCROLL and it["sval"] == SV_SCROLL_DETECT_TREASURE))
        board = parse_snapshot(raw, policy._monrace_knowledge)
        policy._fundraising_mode = None
        for it in board.inventory:
            if it.is_digging_tool or it.is_treasure_detection_scroll:
                self.assertEqual(policy._retention_surplus(board, it), 0)

    def test_all_shelf_pages_are_observed_before_best_tool_is_chosen(self):
        policy, raw, _ = self.shopping_case(gold=600)
        # DECLARED CONSTRUCTED: a two-page General Store with the strongest
        # affordable digger on page two; letters are page-relative.
        full = copy.deepcopy(raw["store"])
        full["page_size"] = 2
        raw["store"] = dict(full, items=copy.deepcopy(full["items"][:2]), page_top=0)
        policy.observe_store_screen(True)
        key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
        self.assertEqual((key, policy.last_reason), (" ", "shop:opening-route-page"))
        page2 = copy.deepcopy(raw)
        page2["store"] = dict(full, items=[dict(full["items"][2], letter="a")], page_top=2)
        self.post(policy, raw, key, page2)
        key = str(policy.choose_key(parse_snapshot(page2, policy._monrace_knowledge)))
        self.assertEqual((key, policy.last_reason), (" ", "shop:opening-route-page"))
        self.post(policy, page2, key, raw)
        policy.observe_store_screen(True)
        key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
        self.assertEqual(key, "pa5\r\r", policy.last_reason)
        bought = self.buy_reply(raw, key)
        self.post(policy, raw, key, bought)
        key = str(policy.choose_key(parse_snapshot(bought, policy._monrace_knowledge)))
        self.assertEqual((key, policy.last_reason), (" ", "shop:opening-route-page"))
        policy.confirm_key_posted(key)
        page2["player"]["gold"] = bought["player"]["gold"]
        page2["inventory"] = copy.deepcopy(bought["inventory"])
        policy.observe_store_screen(True)
        key = str(policy.choose_key(parse_snapshot(page2, policy._monrace_knowledge)))
        self.assertEqual((key, policy.last_reason), ("", "quest:blocked:opening-route"))
        self.assertEqual(policy._opening_q1_failure, "purchase-requires-first-page:fundraising-digger")
        self.assertEqual(policy.fixed_quest_readiness_state()["opening_route_failure"], policy._opening_q1_failure)

    def test_copied_history_pins_the_competing_income_goal_and_oil_unit(self):
        history = self.data["history"]
        throw = next(row for row in history if row["source"] == "bot-decisions.jsonl.3:450")
        self.assertEqual(throw["reason"], "ranged:throw-torch")
        self.assertEqual(throw["fundraising"]["mode"], "mine")
        oil = next(row for row in history if row["source"] == "bot-decisions.jsonl:1788")
        self.assertEqual(oil["optimization_depth"], 20)
        self.assertEqual(oil["key"], "pf1\r\r")
        self.assertEqual(oil["purchase"]["category"], "oil")
        self.assertEqual(oil["readiness"]["strategy_force"]["failed"], ["throwing_items.lit_torch"])
