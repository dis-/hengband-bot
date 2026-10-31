"""Issue #47 R2: two actual fresh-character stops; constructed game replies."""
import tests  # noqa: F401
import copy
import gzip
import json
import pickle
from dataclasses import replace
from pathlib import Path

from hengbot.model import *
from hengbot.town_maps import TownMap
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy_constants import QUEST_STATUS_TAKEN
from tests import test_opening_route_recorded as round1
from tests.test_opening_route_recorded import captured, make_policy
import tests.test_input_executor as executor_harness


class OpeningRouteR2RecordedTest(executor_harness.ProductionHarness):
    post = round1.OpeningRouteRecordedTest.post
    shelf_screen = staticmethod(round1.OpeningRouteRecordedTest.shelf_screen)

    @classmethod
    def setUpClass(cls):
        with gzip.open(Path(__file__).with_name("fixtures") / "opening-route-r2-stops.json.gz",
                       "rt", encoding="utf-8") as stream:
            cls.stops = json.load(stream)

    def case(self, tag):
        policy = make_policy(captured())
        # Source-derived prior town knowledge, loaded by the production CLI.
        values = copy.deepcopy(self.stops["town_map"])
        values["walkable"] = frozenset(Position(*p) for p in values["walkable"])
        values["reward_positions"] = frozenset(Position(*p) for p in values["reward_positions"])
        for name in ("stores", "buildings"):
            values[name] = {int(k): Position(*p) for k, p in values[name].items()}
        for name in ("quest_buildings", "quest_entrances"):
            values[name] = {int(k): frozenset(Position(*p) for p in positions)
                            for k, positions in values[name].items()}
        values["entrance"] = Position(*values["entrance"])
        town_map = TownMap(**values)
        policy._town_map = town_map
        policy._town_maps = {0: town_map}
        facts = copy.deepcopy(self.stops["monrace17"])
        for name in ("flags", "abilities"):
            facts[name] = frozenset(facts[name])
        facts["blows"] = tuple(MonsterBlow(**r) for r in facts["blows"])
        policy._monrace_knowledge[17] = MonraceKnowledge(**facts)
        raw = copy.deepcopy(self.stops[tag]["snapshot"])
        board = parse_snapshot(raw, policy._monrace_knowledge)
        policy.prime(board)
        policy.consume_skill_knowledge(self.stops[tag]["skill"])
        return policy, raw

    def equip_reply(self, raw, key):
        # DECLARED CONSTRUCTED: engine reply equips one identified spare torch.
        following = copy.deepcopy(raw)
        torch = next(it for it in following["inventory"] if it["slot"] == key[1])
        worn = next(it for it in following["equipment"] if it["slot"] == "light")
        following["equipment"].remove(worn)
        replacement = dict(torch, count=1, slot="light", is_equipment=True)
        torch["count"] -= 1
        following["inventory"] = [it for it in following["inventory"] if it["count"]]
        slots = {it["slot"] for it in following["inventory"]}
        worn.update(slot=next(c for c in "abcdefghijklmnopqrstuvw" if c not in slots), is_equipment=False)
        following["inventory"].append(worn)
        following["equipment"].append(replacement)
        following["turn"] += 1
        return following

    def request_and_enter(self, policy, raw):
        # DECLARED CONSTRUCTED: town travel arrival beside Q1's real building.
        # HP, combat stats, inventory, fuel and gold retain the recorded values.
        raw["player"]["y"], raw["player"]["x"] = 27, 98
        key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
        self.assertEqual((key, policy.last_reason), ("8q\x1b", "fixedquest:request"),
                         getattr(policy, "_opening_q1_failure", None))
        accepted = copy.deepcopy(raw)
        accepted["progress"]["quests"].append(dict(id=1, status=QUEST_STATUS_TAKEN,
                                                    fixed=True, level=5, type=6, name="Q1"))
        accepted["player"]["y"] -= 1
        accepted["turn"] += 1
        self.post(policy, raw, key, accepted)
        from hengbot.model import _GRID_TERRAIN_NAMES
        # DECLARED CONSTRUCTED: the public entrance appears after acceptance.
        cell = next(c for c in accepted["grid_map"]["cells"] if c.get("p") == 1)
        cell["q"] = 1
        palette = accepted["grid_map"]["palette"]
        base = next(run[3] for run in accepted["grid_map"]["runs"]
                    if run[0] == cell["y"] and run[1] <= cell["x"] < run[1] + run[2])
        terrain = list(palette[base])
        terrain[2] |= 1 << _GRID_TERRAIN_NAMES.index("quest_enter")
        palette.append(terrain)
        accepted["grid_map"]["runs"].append([cell["y"], cell["x"], 1, len(palette) - 1])
        board = parse_snapshot(accepted, policy._monrace_knowledge)
        pos = min(policy._fixed_quest_entrance_positions(board, 1))
        accepted["player"]["y"], accepted["player"]["x"] = pos.y, pos.x
        policy = pickle.loads(pickle.dumps(policy))
        key = str(policy.choose_key(parse_snapshot(accepted, policy._monrace_knowledge)))
        self.assertEqual((key, policy.last_reason), (">", "quest:enter"))
        inside = copy.deepcopy(accepted)
        inside["floor"].update(in_town=False, quest_id=1, level=5)
        inside["turn"] += 1
        self.post(policy, accepted, key, inside)

    def test_both_actual_stops_keep_the_lantern_request_and_enter_q1(self):
        for tag, gold, hp in (("1", 5, 179), ("2", 11, 104)):
            with self.subTest(seed=tag):
                policy, raw = self.case(tag)
                self.assertEqual(raw["player"]["gold"], gold)
                board = parse_snapshot(raw, policy._monrace_knowledge)
                self.assertEqual((board.player.level, board.player.hp), (7, hp))
                self.assertEqual(policy._count_oil(board), 0)
                self.assertEqual(policy._exact_potion_count(board, SV_POTION_HEALING), 0)
                self.assertEqual(policy._exact_potion_count(board, SV_POTION_SPEED), 0)
                self.assertEqual(self.stops[tag]["before"]["reason"], "quest:blocked:opening-route")
                failure = self.stops[tag]["before"]["fixedquest_readiness"]["opening_route_failure"]
                self.assertIn("light-oil" if tag == "1" else "no-progress:observe:fundraising-digger", failure)
                # No supplier census is seeded: these purses cannot fund a kit.
                # D48 (owner 2026-10-31 「Q1の段階でランタンを松明に持ち替えている」):
                # the worn lantern is never swapped for a torch; the carried
                # torches already satisfy Q1's light gate.
                following = raw
                key = str(policy.choose_key(board))
                self.assertNotEqual(policy.last_reason, "opening-q1:equip-light", key)
                if tag == "2":
                    self.assertEqual(policy.last_reason, "town:kill-mob-approach", key)
                    # DECLARED CONSTRUCTED: posted step brings the recorded cat adjacent.
                    fighting = copy.deepcopy(following)
                    dy, dx = {"1": (1,-1), "2": (1,0), "3": (1,1), "4": (0,-1),
                              "6": (0,1), "7": (-1,-1), "8": (-1,0), "9": (-1,1)}[key]
                    fighting["player"]["y"] += dy; fighting["player"]["x"] += dx
                    fighting["turn"] += 1
                    self.post(policy, following, key, fighting)
                    key = str(policy.choose_key(parse_snapshot(fighting, policy._monrace_knowledge)))
                    self.assertIn(policy.last_reason, {"melee", "town:kill-mob-friendly"}, key)
                    # DECLARED CONSTRUCTED: the attack kills the town cat.
                    calm = copy.deepcopy(fighting)
                    calm["visible_monsters"] = []; calm["detected_monsters"] = []
                    calm["turn"] += 1
                    self.post(policy, fighting, key, calm)
                    following = calm
                    key = str(policy.choose_key(parse_snapshot(following, policy._monrace_knowledge)))
                    self.assertEqual(policy.last_reason, "town:recover", key)
                    # DECLARED CONSTRUCTED: town recovery completes without buying supplies.
                    rested = copy.deepcopy(following)
                    rested["player"]["hp"] = rested["player"]["max_hp"]
                    rested["turn"] += 1
                    self.post(policy, following, key, rested)
                    following = rested
                    key = str(policy.choose_key(parse_snapshot(following, policy._monrace_knowledge)))
                self.assertIn("fixedquest:request:approach", policy.last_reason, key)
                self.assertIsNone(policy._fundraising_mode)
                self.assertIsNone(policy._opening_q1_funding)
                moved = copy.deepcopy(following)
                # DECLARED CONSTRUCTED: one posted town walking step.
                dy, dx = {"1": (1,-1), "2": (1,0), "3": (1,1), "4": (0,-1),
                          "6": (0,1), "7": (-1,-1), "8": (-1,0), "9": (-1,1)}[key]
                moved["player"]["y"] += dy; moved["player"]["x"] += dx
                moved["turn"] += 1
                self.post(policy, following, key, moved)
                self.request_and_enter(policy, moved)

    def test_known_lantern_or_torch_with_visit_fuel_needs_no_spare_oil(self):
        policy, raw = self.case("1")
        board = parse_snapshot(raw, policy._monrace_knowledge)
        required = policy._q1_visit_light_fuel(board)
        for sval in (SV_LITE_TORCH, SV_LITE_LANTERN):
            with self.subTest(sval=sval):
                equipment = tuple(replace(it, known=True, sval=sval, fuel=int(required))
                                  if it.is_light else it for it in board.equipment)
                enough = replace(board, equipment=equipment)
                self.assertTrue(policy._fixed_quest_ready(enough, 1), policy.fixed_quest_readiness_state())
                self.assertEqual(policy.fixed_quest_readiness_state()["simultaneous_melee"], 1)
                short = replace(enough, equipment=tuple(replace(it, fuel=int(required)-1)
                                                       if it.is_light else it for it in equipment))
                # Q1 now accepts the recorded usable carried torches even
                # when the worn light is short of the full-visit estimate.
                self.assertTrue(policy._fixed_quest_ready(short, 1))
                self.assertEqual(policy.fixed_quest_readiness_state()["reason"], "ready")

    def test_other_once_quests_keep_the_spare_oil_gate(self):
        policy, raw = self.case("1")
        board = parse_snapshot(raw, policy._monrace_knowledge)
        # DECLARED CONSTRUCTED: reuse Q1's safe force/roster as Q2 (an ONCE quest without Q34's opening lantern);
        # only the identity changes, so no unrelated force gate hides the light gate.
        policy._quest_knowledge[2] = replace(policy._quest_knowledge[1], id=2)
        policy._quest_strategies[2] = replace(policy.approved_quest_strategy(1), quest_id=2)
        board = replace(board, equipment=tuple(replace(it, known=True, fuel=7500)
                                               if it.is_light else it for it in board.equipment))
        self.assertFalse(policy._fixed_quest_ready_for_travel(board, 2))
        self.assertEqual(policy.fixed_quest_readiness_state()["reason"], "light-oil")

    def test_required_potions_still_use_the_existing_black_market_supplier(self):
        round1.OpeningRouteRecordedTest.setUpClass()
        helper = round1.OpeningRouteRecordedTest()
        policy, raw, _ = helper.shopping_case(hp=80)
        raw["store"] = None
        raw["inventory"].append(dict(helper.data["seeds"]["general"]["snapshot"]["store"]["items"][8],
                                     slot="t", count=5))
        # DECLARED CONSTRUCTED: the lower force tier's mandatory potion offers,
        # a surveyed empty temple, and the existing Black Market supplier.
        page = copy.deepcopy(helper.data["seeds"]["general"]["snapshot"]["store"])
        page["store_type"] = STORE_BLACK
        page["items"] = [dict(letter=letter, name="required potion", tval=TVAL_POTION,
                              sval=sval, price=1, count=count, known=True, aware=True, charging=False)
                         for letter, sval, count in (("a", SV_POTION_HEALING, 2),
                                                    ("b", SV_POTION_SPEED, 1))]
        page["stock_num"] = len(page["items"])
        raw["store"] = page
        policy._town_supplier_stock[STORE_TEMPLE] = StoreState(STORE_TEMPLE, [])
        policy._town_supplier_stock_observations[STORE_TEMPLE] = (0, raw["turn"])
        for expected in ("a", "a"):
            policy.observe_store_screen(True)
            key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
            self.assertEqual((key[:2], policy.last_reason), ("p" + expected, "shop:in-store-buy"))
            following = helper.buy_reply(raw, key)
            self.post(policy, raw, key, following)
            raw = following
