"""2026-10-30 n1-c: the Magic-Eater town stops D9 (after Q1) and Lv7 (before Q1).

D9 (lives 021, 022, 024): after Q1 the staff sequence claimed every shop page
in its buy phase, so the explicit-target fundraising run could not buy its
light, oil or detection kit; every supplier visit was observe-and-leave, the
restock waits repeated and the town owners retired.  Life 024 also walked
Home through a walled detour that the progress test judged no-progress, so
another supplier's approach replaced every other step.
Lv7 (life 023): the class-16 Q1 fallback melee floor 4.58 failed the recorded
3.85, so the opening route demanded two Healing and one Speed potion it could
not buy and stopped on quest:blocked:opening-route.

Each case starts on the recorded board with the recorded shelves.  Only the
replies to newly posted keys are constructed (marked below); every decision
goes through the public chooser and the production executor.
"""
import tests  # noqa: F401

import copy
import gzip
import json
from pathlib import Path

from hengbot import me_staff_sequence
from hengbot.model import parse_snapshot
from hengbot.policy_constants import STORE_HOME, TOWN_TRAVEL_STORE_SYMBOLS
from tests import test_lv7_town_stop_recorded as lv7
import tests.test_input_executor as executor_harness


FIXTURE = Path(__file__).with_name("fixtures") / "me-town-stops-20261030.json.gz"
DIRECTIONS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
              "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}
STOPS = ("town:blocked:", "quest:blocked:")


class MagicEaterTownStopsRecordedTest(executor_harness.ProductionHarness):
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)
    post = lv7.Lv7TownStopRecordedTest.post

    @classmethod
    def setUpClass(cls):
        lv7.Lv7TownStopRecordedTest.setUpClass()
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.cases = {case["id"].split("/")[0]: case for case in json.load(stream)}

    def boundary(self, life, *, kit_bought=False):
        case = self.cases[life]
        policy, raw = lv7.Lv7TownStopRecordedTest().boundary(dict(
            monraces=case["monraces"], snapshot=case["board"], knowledge=case["knowledge"],
            state={"modes_and_latches": case["state"]}), kit_bought=kit_bought)
        # DECLARED CONSTRUCTED: this process already read the game's staff
        # power list (me_staff_sequence.read_powers, #47).
        me_staff_sequence.state(policy).powers_read = True
        target = case["supply_stockout_gold_target"]
        if target is not None:
            # DECLARED RECONSTRUCTED: the capture keeps the fundraising mode
            # and its explicit gold target, not the staff sequence's own
            # record; that record named this same target when it began the
            # run (me-staff:fundraise:* reasons of the same life).
            policy._fundraising_mode = case["state"]["_fundraising_mode"]
            policy._supply_stockout_gold_target = target
            policy._planned_mining_runs, policy._mining_runs_completed = 1, 0
            record = me_staff_sequence.state(policy)
            record.fundraise_target, record.fundraise_runs = target, 1
        return policy, raw

    def reply(self, policy, raw, key, case):
        """DECLARED CONSTRUCTED: the engine's reply to the posted key."""
        cells = {(y, x): store for y, x, store in case["store_cells"]}
        entrance = {store: (y, x) for (y, x), store in cells.items()}
        pages = self.pages
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["messages"] = []
        here = (raw["player"]["y"], raw["player"]["x"])
        if raw.get("store"):
            following["store"] = None
            if key.startswith("p"):
                ware = next(it for it in raw["store"]["items"] if it["letter"] == key[1])
                quantity = int(key.removesuffix("\x1b")[2:].strip() or 1)
                slots = {it["slot"] for it in following["inventory"]}
                item = dict(ware, count=quantity,
                            slot=next(c for c in "abcdefghijklmnopqrstuvw" if c not in slots))
                item.pop("letter")
                item.pop("price")
                following["inventory"].append(item)
                following["player"]["gold"] -= ware["price"] * quantity
                page = copy.deepcopy(raw["store"])
                next(it for it in page["items"] if it["letter"] == key[1])["count"] -= quantity
                pages[str(page["store_type"])] = page
                self.bought.append((ware["name"], quantity))
        elif key in DIRECTIONS:
            dy, dx = DIRECTIONS[key]
            following["player"]["y"], following["player"]["x"] = here[0] + dy, here[1] + dx
            # Walking onto a shop entrance enters it.
            following["store"] = pages.get(str(cells.get((here[0] + dy, here[1] + dx))))
        elif key == "5" and here in cells and str(cells[here]) in pages:
            following["store"] = pages[str(cells[here])]
        elif key.startswith("\x1b`n"):
            store = TOWN_TRAVEL_STORE_SYMBOLS.index(key[3])
            following["player"]["y"], following["player"]["x"] = entrance[store]
            following["store"] = pages.get(str(store))
        elif key.startswith("w"):
            following = lv7.Lv7TownStopRecordedTest.equip_reply(raw, key)
            following["turn"] += 9
        elif key.lstrip("\\").startswith("F"):
            oil = next(it for it in following["inventory"] if it["slot"] == key.lstrip("\\")[1])
            oil["count"] -= 1
            following["inventory"] = [it for it in following["inventory"] if it["count"]]
            light = next(it for it in following["equipment"] if it["slot"] == "light")
            light["light_turns"] = light["fuel"] = min(15000, (light.get("light_turns") or 0) + 7500)
        if following.get("store") and following["store"]["store_type"] == STORE_HOME:
            following["store"] = None
        return following

    def drive(self, life, *, limit, done, kit_bought=False):
        case = self.cases[life]
        policy, raw = self.boundary(life, kit_bought=kit_bought)
        self.pages = copy.deepcopy(case["pages"])
        self.case_cells = case["store_cells"]
        self.bought, reasons = [], []
        for _ in range(limit):
            key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
            reasons.append(policy.last_reason)
            if done(policy, raw, key):
                return policy, raw, reasons
            self.assertNotEqual(key, "", reasons[-8:])
            self.assertFalse(policy.last_reason.startswith(STOPS), reasons[-8:])
            following = self.reply(policy, raw, key, case)
            self.post(policy, raw, key, following)
            raw = following
        self.fail(("no progress", self.bought, reasons[-12:]))

    def at_home(self, policy, raw, key):
        home = next((y, x) for y, x, store in self.case_cells if store == STORE_HOME)
        return (raw["player"]["y"], raw["player"]["x"]) == home

    def test_recorded_stops(self):
        for life in ("life-021", "life-022", "life-024"):
            recorded = self.cases[life]["recorded"]
            self.assertEqual(recorded["kind"], "town:blocked:owner-retired-burst")
        # The kit supplier page was observed and wanted, yet refused.
        selector = self.cases["life-024"]["recorded"]["shop_selector"]
        self.assertEqual((selector["rejection_reason"], selector["wanted_purchase"]["category"]),
                         ("preempted", "lantern"))
        readiness = self.cases["life-023"]["recorded"]["fixedquest_readiness"]
        self.assertEqual(self.cases["life-023"]["recorded"]["reason"], "quest:blocked:opening-route")
        self.assertEqual(readiness["opening_route_failure"], "stop:stock:quest-healing")
        self.assertEqual(readiness["strategy_force"]["dps"], {"measured": 3.85, "required": 4.58})

    def test_staff_sequence_leaves_the_kit_shelves_to_the_ordinary_order(self):
        # The staff sequence still owns a page that sells an affordable staff;
        # these General store / Alchemist pages sell none.
        for life in ("life-021", "life-022", "life-024"):
            with self.subTest(life=life):
                policy, raw = self.boundary(life)
                board = parse_snapshot(raw, policy._monrace_knowledge)
                self.assertTrue(me_staff_sequence.applies(policy, board))
                self.assertEqual(me_staff_sequence._phase(policy, board), "buy")
                self.assertFalse(me_staff_sequence.shopping(policy, board))
                self.assertIsNotNone(policy._next_purchase(board))

    def test_life_022_buys_its_light_and_walks_into_the_mine(self):
        _, _, reasons = self.drive("life-022", limit=80,
                                   done=lambda policy, raw, key: key.startswith(">"))
        self.assertEqual(self.bought, [("真鍮のランタン(7500ターンの寿命) {明}", 1)])
        self.assertEqual(reasons[-1], "descend")

    def test_life_024_buys_the_kit_and_reaches_home(self):
        _, raw, _ = self.drive("life-024", limit=140, done=self.at_home)
        names = [name for name, _ in self.bought]
        self.assertIn("真鍮のランタン(7500ターンの寿命) {明}", names)
        self.assertIn("財宝感知の巻物", names)
        self.assertLess(raw["player"]["gold"], 2000)

    def test_life_021_buys_detection_and_oil_and_reaches_home(self):
        self.drive("life-021", limit=200, done=self.at_home)
        names = [name for name, _ in self.bought]
        self.assertIn("財宝感知の巻物", names)
        self.assertIn("油つぼ", names)

    def test_life_023_buys_torches_and_requests_q1(self):
        board_policy, raw = self.boundary("life-023")
        board = parse_snapshot(raw, board_policy._monrace_knowledge)
        self.assertEqual([row[1:3] for row in board_policy._opening_q1_requirements(board)],
                         [(20, 10), (0, 0), (0, 0)])
        # DECLARED CONSTRUCTED (kit_bought=True): the optional mining-kit
        # survey of shelves this capture never observed is marked done.
        self.drive("life-023", limit=80, kit_bought=True,
                   done=lambda policy, raw, key: policy.last_reason == "fixedquest:request")
        self.assertEqual(self.bought, [("松明(2500ターンの寿命) {明}", 10)])
        # Without it the route continues to that bounded survey, not a block.
        self.drive("life-023", limit=6, done=lambda policy, raw, key: (
            policy.last_reason == "shop:travel" and bool(self.bought)))


if __name__ == "__main__":
    import unittest
    unittest.main()
