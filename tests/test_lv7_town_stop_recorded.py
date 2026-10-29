"""Issue #47: eight recorded 10/29 boundaries, public chooser/follow sender.

Diagnostic JSON is not a pickle checkpoint. We reconstruct the single active
equipment action from transaction_next and its source item, and supplier pages
from the recorded observations. Replies to new keys are declared constructed.
No readiness, ownership, purchase or executor method is mocked.
"""
import tests  # noqa: F401

import copy
import gzip
import io
import json
from pathlib import Path
import time

from hengbot.cli import (
    PostingContract, TRAVEL_MACRO_TRIGGERS, _ExecutorInputPort,
    _send_decision_key_with_prompt_chain,
)
from hengbot.equipment_optimizer import equipment_identity, equipment_move_identity
from hengbot.equipment_transaction_planner import EquipmentTransaction, EquipmentTransactionPlan
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.model import StoreItem, StoreState, _GRID_TERRAIN_NAMES, _parse_items, parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy_constants import QUEST_STATUS_TAKEN
from tests import test_opening_route_r2_recorded as round2
import tests.test_input_executor as executor_harness
from tests.test_input_executor import FaithfulHookGame, command_screen, prompt_screen


FIXTURE = Path(__file__).with_name("fixtures") / "lv7-town-stop-20261029.json.gz"


def supplier_reply(page):
    """Re-emit only the fields the captured protocol actually exported."""
    page = copy.deepcopy(page)
    items = []
    for item in page["items"]:
        raw = {key: item[key] for key in item["exported_fields"] if key in item}
        raw["damage_dice"] = dict(num=item["damage_dice_num"], sides=item["damage_dice_sides"])
        items.append(raw)
    page["items"] = items
    return {key: value for key, value in page.items() if value is not None}


class Lv7TownStopRecordedTest(executor_harness.ProductionHarness):
    @staticmethod
    def shelf_screen(raw):
        # Same height as these live runs; 21/52-row shelves do not fit the
        # 24-line transport harness's default test screen.
        screen = command_screen(raw["turn"])
        screen.update(height=68, width=213, lines=[""] * 68,
                      cursor=dict(visible=True, y=60, x=0))
        screen["lines"][60] = " " * 66 + "You may: p) Purchase an item. s) Sell an item."
        screen["lines"][61] = " " * 66 + " ESC) Exit from Building."
        for index, item in enumerate(raw["store"]["items"]):
            screen["lines"][6 + index] = f"{item['letter']}) {item['name']}"
        return screen

    @classmethod
    def setUpClass(cls):
        round2.OpeningRouteR2RecordedTest.setUpClass()
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.cases = json.load(stream)

    def boundary(self, case, *, kit_bought=False):
        policy, _ = round2.OpeningRouteR2RecordedTest().case("1")
        for key, facts in case["monraces"].items():
            facts = copy.deepcopy(facts)
            for name in ("flags", "abilities"):
                facts[name] = frozenset(facts[name])
            facts["blows"] = tuple(MonsterBlow(**row) for row in facts["blows"])
            policy._monrace_knowledge[int(key)] = MonraceKnowledge(**facts)
        raw = copy.deepcopy(case["snapshot"])
        policy.prime(parse_snapshot(raw, policy._monrace_knowledge))
        for row in case["knowledge"]:
            category = row["knowledge"]["category"]
            if category == "skill_exp":
                policy.consume_skill_knowledge(row)
            if category == "home":
                policy.consume_home_knowledge(_parse_items(row["knowledge"]["items"], protocol=3))
        modes = case["state"]["modes_and_latches"]
        for key, page in modes.get("_town_supplier_stock", {}).items():
            page = copy.deepcopy(page)
            for item in page["items"]:
                for name in ("known_flags", "exported_fields"):
                    item[name] = frozenset(item[name])
            page["items"] = [StoreItem(**item) for item in page["items"]]
            policy._town_supplier_stock[int(key)] = StoreState(**page)
        policy._town_supplier_stock_observations = {
            int(key): tuple(value) for key, value in modes.get("_town_supplier_stock_observations", {}).items()
        }
        policy._opening_q1_kit_bought = kit_bought
        return policy, raw

    def resume_equipment(self, policy, case):
        # DECLARED RECONSTRUCTED: captures omit session objects, but expose
        # this exact single unposted action, target and original pack item.
        action = case["decisions"][-1]["equipment_optimization"]["transaction_next"]
        item = _parse_items([case["transaction_item"]], protocol=3)[0]
        transaction = EquipmentTransaction(
            **action, item_identity=equipment_identity(item),
            move_identity=equipment_move_identity(item),
        )
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((transaction,), (), len(case["snapshot"]["inventory"]))
        )

    def test_recorded_population_pins_the_three_failure_paths(self):
        self.assertEqual([case["snapshot"]["turn"] for case in self.cases],
                         [75424, 81070, 80759, 79942, 81089, 82183, 83268, 80569])
        for case in self.cases:
            last = case["decisions"][-1]
            if "owner-retired-burst" in case["id"]:
                retired = [row for row in case["decisions"]
                           if row.get("arbiter", {}).get("retired")][-3:]
                self.assertEqual(len(retired), 3)
                for row in retired:
                    self.assertEqual(row["arbiter"]["producer_owner"], "detectors")
                    self.assertEqual(row["town_idle_d0"]["trigger_category"], "recurrence")
                    self.assertEqual(row["town_idle_d0"]["recurrence_count"], 2)
                equipment = last["equipment_optimization"]
                self.assertEqual(equipment["transaction_next"]["target_slot"], "light")
                self.assertIsNone(equipment["transaction_pending"])
                self.assertTrue(any(work and work.startswith("route-refused:")
                                    for row in case["decisions"][-6:]
                                    for work in row["offered_work_ids"]))
            else:
                failure = last["fixedquest_readiness"]["opening_route_failure"]
                self.assertEqual(failure, "quest-entry-unavailable" if "life-400" in case["id"]
                                 else "no-progress:fundraising-digger")
                self.assertEqual(last["key"], "")

    def post(self, policy, raw, key, following):
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.jsonl = [copy.deepcopy(raw)]
        game.screen = self.shelf_screen(raw) if raw.get("store") else command_screen(raw["turn"])
        screens, expected = [], [TRAVEL_MACRO_TRIGGERS.get(key, key)]
        if policy.last_reason == "shop:one-shot-buy" and key.startswith("p"):
            body = key.removesuffix("\x1b")
            expected = [body[:2]]
            tail = body[2:]
            quantity = int(tail.strip() or 1)
            ware = next(item for item in raw["store"]["items"] if item["letter"] == key[1])
            if tail.endswith("\r\r"):
                screens.append(prompt_screen(f"いくつですか (1-{ware['count']}): 1"))
                expected.append(tail[:-1])
                tail = "\r"
            screens += [prompt_screen(f"Do you buy for ${ware['price'] * quantity}? [Y/n]"),
                        self.shelf_screen(raw)]
            expected += [tail, "\x1b"]
        if key.startswith("w"):
            screens = [prompt_screen("(Inven: a-w, ESC) どれを装備しますか?")]
            expected = ["w", key[1:]]
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
            port, "lv7-stop-replay", key, None, set(), policy=policy,
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

    @staticmethod
    def equip_reply(raw, key):
        following = copy.deepcopy(raw)
        item = next(it for it in following["inventory"] if it["slot"] == key[1])
        worn = next((it for it in following["equipment"] if it["slot"] == "light"), None)
        if worn is not None:
            following["equipment"].remove(worn)
            slots = {it["slot"] for it in following["inventory"]}
            worn["slot"] = next(c for c in "abcdefghijklmnopqrstuvw" if c not in slots)
            following["inventory"].append(worn)
        following["equipment"].append(dict(item, count=1, slot="light", is_equipment=True))
        item["count"] -= 1
        following["inventory"] = [it for it in following["inventory"] if it["count"]]
        following["turn"] += 1
        return following

    def test_four_bursts_execute_the_unposted_light_action(self):
        captures = [case for case in self.cases if "owner-retired-burst" in case["id"]]
        self.assertEqual(len(captures), 4)
        for case in captures:
            with self.subTest(capture=case["id"]):
                policy, raw = self.boundary(case)
                self.resume_equipment(policy, case)
                self.assertFalse(policy._equipment_transaction_owned_items)
                key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
                if "life-227" in case["id"]:
                    # The selected torch became fully known while its owner
                    # was starved. Its old identity is now invalid; execute
                    # the existing abandonment before deriving fresh work.
                    self.assertEqual((key, policy.last_reason),
                                     ("5", "equipment-transaction:equip-item-missing"))
                    self.assertIsNone(policy._equipment_transaction_session)
                    following = copy.deepcopy(raw)
                    following["turn"] += 1
                    self.post(policy, raw, key, following)
                    raw = following
                    key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
                    self.assertNotIn(key, ("", "5"), policy.last_reason)
                    self.assertFalse(policy.last_reason.startswith(("town:blocked:", "quest:blocked:")))
                    continue
                self.assertEqual(policy.last_reason, "equipment-transaction:equip", key)
                self.assertTrue(key.startswith("w"))
                following = self.equip_reply(raw, key)
                self.post(policy, raw, key, following)
                self.assertIsNotNone(policy._equipment_transaction_session.pending_action)
                # DECLARED CONSTRUCTED: engine confirms the exact posted equip.
                next_key = str(policy.choose_key(parse_snapshot(following, policy._monrace_knowledge)))
                self.assertFalse(policy.last_reason.startswith(("town:blocked:", "quest:blocked:")),
                                 (next_key, policy.last_reason))
                session = policy._equipment_transaction_session
                self.assertTrue(session is None or session.complete)
                if case["id"].startswith("me-a/"):
                    self.continue_q34(policy, following, case, next_key)

    def continue_q34(self, policy, raw, case, key):
        """Construct replies to the observed shelf, then request and enter Q34."""
        self.assertEqual(policy.last_reason, "shop:approach")
        page = copy.deepcopy(case["pages"]["0"]["store"])
        purchased = False
        for _ in range(12):
            reason = policy.last_reason
            following = copy.deepcopy(raw)
            following["turn"] += 1
            if reason == "shop:approach":
                goal = policy._town_map.store_position(0)
                following["player"].update(y=goal.y, x=goal.x)
                following["store"] = page
            elif key == "\x1b":
                following["store"] = None
            elif reason == "shop:one-shot-buy" and key == "5":
                following["store"] = page
            elif key.startswith("p"):
                ware = next(it for it in page["items"] if it["letter"] == key[1])
                self.assertEqual(ware["tval"], 39)
                # One replacement for the throwing torch now worn as light.
                slots = {it["slot"] for it in raw["inventory"]}
                item = dict(ware, count=1, slot=next(c for c in "abcdefghijklmnopqrstuvw"
                                                   if c not in slots))
                item.pop("letter", None)
                item.pop("price", None)
                following["inventory"].append(item)
                following["player"]["gold"] -= ware["price"]
                following["store"] = None
                purchased = True
            elif reason == "fixedquest:request:approach":
                self.assertTrue(purchased)
                board = parse_snapshot(raw, policy._monrace_knowledge)
                goal = min(policy._fixed_quest_building_positions(board, 34))
                following["player"].update(y=goal.y + 1, x=goal.x)
            elif reason == "fixedquest:request":
                self.assertEqual(key, "8q\x1b")
                following["progress"]["quests"].append(
                    dict(id=34, status=QUEST_STATUS_TAKEN, fixed=True, level=5, type=6, name="Q34"))
                following["player"]["y"] -= 1
                # DECLARED CONSTRUCTED: acceptance exposes the public entrance.
                goal = min(policy._fixed_quest_building_positions(
                    parse_snapshot(raw, policy._monrace_knowledge), 34))
                palette = following["grid_map"]["palette"]
                base = next(run[3] for run in following["grid_map"]["runs"]
                            if run[0] == goal.y and run[1] <= goal.x < run[1] + run[2])
                terrain = list(palette[base])
                terrain[2] |= 1 << _GRID_TERRAIN_NAMES.index("quest_enter")
                palette.append(terrain)
                following["grid_map"]["runs"].append([goal.y, goal.x, 1, len(palette) - 1])
                following["grid_map"]["cells"].append(dict(y=goal.y, x=goal.x, q=34))
            elif reason == "quest:enter:approach":
                board = parse_snapshot(raw, policy._monrace_knowledge)
                goal = min(policy._fixed_quest_entrance_positions(board, 34))
                following["player"].update(y=goal.y, x=goal.x)
            elif reason == "quest:enter":
                self.assertEqual(key, ">")
                self.assertTrue(purchased)
                self.assertTrue(policy._fixed_quest_ready(
                    parse_snapshot(raw, policy._monrace_knowledge), 34),
                    policy.fixed_quest_readiness_state())
                following["floor"].update(in_town=False, quest_id=34, level=5)
                self.post(policy, raw, key, following)
                return
            else:
                self.fail((key, reason, policy.fixed_quest_readiness_state()))
            self.post(policy, raw, key, following)
            raw = following
            key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
        self.fail((key, policy.last_reason))

    def test_magic_eater_full_q34_gate_keeps_supplies_hp_and_light_requirements(self):
        case = self.cases[0]
        self.assertTrue(case["id"].startswith("me-a/"))
        for change, expected in (("ready", "ready"), ("hp", "strategy-force"),
                                 ("torches", "strategy-force"), ("fuel", "light-torch-only")):
            with self.subTest(change=change):
                policy, raw = self.boundary(case)
                if change == "hp":
                    raw["player"].update(hp=29, max_hp=29)
                if change == "torches":
                    torch = next(it for it in raw["inventory"] if it.get("tval") == 39)
                    torch["count"] -= 1
                if change == "fuel":
                    raw = self.equip_reply(raw, "wb")
                    # Replace the worn torch's consumed throwing reserve,
                    # but leave every torch below the opening's fuel floor.
                    torch = next(it for it in raw["inventory"] if it.get("tval") == 39)
                    torch["count"] += 1
                    for it in raw["inventory"] + raw["equipment"]:
                        if it.get("tval") == 39:
                            it["light_turns"] = 99
                ready = policy._fixed_quest_ready(parse_snapshot(raw, policy._monrace_knowledge), 34)
                details = policy.fixed_quest_readiness_state()
                self.assertEqual(details["reason"], expected, details)
                self.assertEqual(ready, change == "ready")
                if ready:
                    self.assertEqual(details["max_damage_ratio"], 1.0)
                    self.assertGreater(details["entry_melee_hp"], 0)
                    self.assertLessEqual(details["entry_melee_hp"], 8)
                    self.assertGreaterEqual(details["entry_melee_output"], 3.5)

    def test_ready_q1_entrance_resolves_its_adjacent_monster_before_entry(self):
        case = self.cases[1]
        self.assertIn("life-400", case["id"])
        policy, raw = self.boundary(case, kit_bought=True)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertTrue(policy._fixed_quest_ready(board, 1))
        self.assertEqual(len(policy._physical_adjacent_hostiles(board)), 1)
        key = str(policy.choose_key(board))
        self.assertEqual((key, policy.last_reason), ("7", "melee"))
        # DECLARED CONSTRUCTED: the posted attack removes the adjacent monster.
        following = copy.deepcopy(raw)
        following["visible_monsters"] = []
        following["turn"] += 1
        self.post(policy, raw, key, following)
        key = str(policy.choose_key(parse_snapshot(following, policy._monrace_knowledge)))
        self.assertEqual(policy.last_reason, "quest:enter:approach", key)
        self.assertNotEqual(key, "")
        arrival = copy.deepcopy(following)
        goal = min(policy._fixed_quest_entrance_positions(
            parse_snapshot(following, policy._monrace_knowledge), 1))
        arrival["player"].update(y=goal.y, x=goal.x)
        arrival["turn"] += 1
        self.post(policy, following, key, arrival)
        key = str(policy.choose_key(parse_snapshot(arrival, policy._monrace_knowledge)))
        self.assertEqual((key, policy.last_reason), (">", "quest:enter"))

    def test_three_supplier_stops_buy_instead_of_repeating_unbindable_sale(self):
        captures = [case for case in self.cases if "life-226" in case["id"]
                    and "no-key" in case["id"]]
        self.assertEqual(len(captures), 3)
        for case in captures:
            with self.subTest(capture=case["id"]):
                policy, raw = self.boundary(case)
                # The incident JSON omits OpeningRoute's page census. Black
                # retains only page 2 (12 of 64 rows), so a restart correctly
                # surveys it again. Do not invent the missing first 52 rows.
                key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
                self.assertEqual(policy.last_reason, "shop:travel")
                # DECLARED CONSTRUCTED: a subsequent Black restock contains
                # just the 12 retained rows, then we observe General again.
                black = supplier_reply(case["state"]["modes_and_latches"]["_town_supplier_stock"]["6"])
                black.update(stock_num=len(black["items"]), page_top=0)
                survey = copy.deepcopy(raw)
                survey["store"] = black
                goal = policy._town_map.store_position(6)
                survey["player"].update(y=goal.y, x=goal.x)
                survey["turn"] += 1
                self.post(policy, raw, key, survey)
                key = str(policy.choose_key(parse_snapshot(survey, policy._monrace_knowledge)))
                self.assertEqual(key, "\x1b", policy.last_reason)
                outside = copy.deepcopy(survey)
                outside["store"] = None
                outside["turn"] += 1
                self.post(policy, survey, key, outside)
                key = str(policy.choose_key(parse_snapshot(outside, policy._monrace_knowledge)))
                self.assertIn(policy.last_reason, ("shop:travel", "shop:approach"))
                general = copy.deepcopy(raw)
                general["store"] = copy.deepcopy(case["pages"]["0"]["store"])
                general["turn"] = outside["turn"] + 1
                self.post(policy, outside, key, general)
                key = str(policy.choose_key(parse_snapshot(general, policy._monrace_knowledge)))
                self.assertEqual(key, "\x1b", policy.last_reason)
                raw = copy.deepcopy(general)
                raw["store"] = None
                raw["turn"] += 1
                self.post(policy, general, key, raw)
                key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
                self.assertEqual(policy.last_reason, "shop:one-shot-buy", key)
                self.assertEqual(key, "5")
                self.assertTrue(policy._store_visit.operation_key.startswith("p"))
                # Entry is posted alone; the purchase tail waits for a fresh
                # actual store page, as in the production one-shot protocol.
                opened = copy.deepcopy(raw)
                opened["store"] = copy.deepcopy(case["pages"]["0"]["store"])
                opened["turn"] += 1
                self.post(policy, raw, key, opened)
                raw = opened
                key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
                self.assertTrue(key.startswith("p"), (key, policy.last_reason))
                # DECLARED CONSTRUCTED: purchase succeeds at the observed row.
                following = copy.deepcopy(raw)
                ware = next(it for it in case["pages"]["0"]["store"]["items"] if it["letter"] == key[1])
                self.assertEqual(ware["tval"], 20)
                slots = {it["slot"] for it in raw["inventory"]}
                slot = next(c for c in "abcdefghijklmnopqrstuvw" if c not in slots)
                item = dict(ware, count=1, slot=slot, is_equipment=True)
                item.pop("letter", None)
                item.pop("price", None)
                following["inventory"].append(item)
                following["player"]["gold"] -= ware["price"]
                following["store"] = None
                following["turn"] += 1
                self.post(policy, raw, key, following)
