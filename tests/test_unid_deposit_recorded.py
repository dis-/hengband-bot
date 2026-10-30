"""D29 root 2: equipment waiting for identification is shelved, not carried.

Recorded n1-a life-427 stop (2026-10-30 08:37, turn 406215): 19 items in the
pack (4 free, the terminal reserve), Identify staves of 16 charges, and a
16-charge staff on the Magic shelf for 910 of the 5,346 gold.  The purchase
needed a fifth free slot (town_pack_budget.permits), while four carried
equipment items waited for *Identify* that the observed Alchemist shelf did
not sell.  Home's deposit pass kept them as identification-flow candidates,
so no owner could make the room and departure stopped with
departure_block.failed ["identify_staff_ready"].

Owner 2026-10-31: 「鑑定待ちの装備は預ける　極力持ち歩かない」 and
「当然だが、預けた装備を取り出して鑑定する処理が別途必要」.

The test attaches the recorded visit to the established static-game policy
helper (DECLARED RECONSTRUCTED: the arrival board primes it, the visit's
observed shop pages and Home answers are consumed through the production
response consumer and filed as supplier stock; the skill census is
constructed to isolate town work).  From the stop board every key comes from
the public chooser and goes through the production executor; the engine's
replies are constructed (marked below).  Fixture:
tests/extract_unid_deposit_fixture.py.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import io
import json
from pathlib import Path
import re
import tempfile
import time

from hengbot.cli import (
    PostingContract, _ExecutorInputPort, _consume_response_sequence,
    _send_decision_key_with_prompt_chain,
)
from hengbot.model import SV_STAFF_IDENTIFY, TVAL_STAFF, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import STORE_HOME, TOWN_TRAVEL_STORE_SYMBOLS
from tests import test_lv7_town_stop_recorded as lv7
from tests.test_esp_threat_rest_recorded import EDIT, _policy
import tests.test_input_executor as executor_harness


FIXTURE = Path(__file__).with_name("fixtures") / "unid-deposit-20261030.json.gz"
DIRECTIONS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
              "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}
LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
WAITING = ("長持ちの真鍮のランタン", "殺戮のセスタス", "毒殺のマン・ゴーシュ", "★サーベル")
# The pre-departure character dump is issued only once departure is ready.
DEPARTURE = ("town:recall-", "town:travel-entrance", "town:character-dump")


class UnidentifiedDepositRecordedTest(executor_harness.ProductionHarness):
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)
    shop_post = lv7.Lv7TownStopRecordedTest.post

    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        super().setUp()
        self.directory = Path(tempfile.mkdtemp())
        self.cells = {(y, x): store for y, x, store in self.case["store_cells"]}
        self.entrance = {store: cell for cell, store in self.cells.items()}
        self.pages = {}
        for row in self.case["observations"]:
            if row["type"] == "store":
                self.pages[row["store"]["store_type"]] = copy.deepcopy(row["store"])
        self.events = []

    def consume(self, policy, row):
        _consume_response_sequence(
            [json.dumps(row, ensure_ascii=False)], policy, lambda _key: True,
            self.monrace, knowledge_ledger_path=self.directory / "knowledge.jsonl")

    def boundary(self):
        policy = _policy(self.directory, self.monrace)
        # The viewing bots run with these startup flags (bot-stderr.log).
        policy._crossarea_fundraising_enforced = True
        policy._in_store_ops_enabled = True
        arrival = parse_snapshot(copy.deepcopy(self.case["arrival"]), policy._monrace_knowledge)
        policy.prime(arrival)
        for row in self.case["observations"]:
            if row["type"] == "knowledge" and row["knowledge"]["category"] == "home":
                policy._home_knowledge_scan_inflight = True
                policy._home_knowledge_scan_epoch = None
            self.consume(policy, row)
            if row["type"] == "store":
                page = parse_snapshot(copy.deepcopy(row), policy._monrace_knowledge)
                policy._town_supplier_stock[page.store.store_type] = page.store
                policy._town_supplier_stock_observations[page.store.store_type] = (
                    policy._effective_town_id(page), page.turn)
        raw = copy.deepcopy(self.case["board"])
        policy._skill_exp_cache = (0, 0, raw["player"]["level"], policy._town_visit_epoch)
        return policy, raw

    # ------------------------------------------------------------ replies
    @staticmethod
    def relabel(items):
        for index, item in enumerate(items):
            item["slot"] = LETTERS[index]

    def home_reply(self, following, page, body):
        """DECLARED CONSTRUCTED: store.cpp Home deposit (d) and take (p)."""
        operations = re.findall(r"([dp])([a-zA-Z])(?:(\d+)\r)?", body)
        for command, letter, quantity in operations:
            if command == "d":
                item = next(it for it in following["inventory"] if it["slot"] == letter)
                count = int(quantity or item["count"])
                moved = dict(item, count=count)
                moved.pop("slot")
                item["count"] -= count
                following["inventory"] = [it for it in following["inventory"] if it["count"]]
                page["items"].append(moved)
                self.events.append(("deposit", moved["name"]))
            else:
                ware = next(it for it in page["items"] if it["letter"] == letter)
                count = int(quantity or 1)
                taken = dict(ware, count=count)
                taken.pop("letter")
                taken.pop("price", None)
                following["inventory"].append(taken)
                ware["count"] -= count
                page["items"] = [it for it in page["items"] if it["count"]]
                self.events.append(("withdraw", taken["name"]))
            self.relabel(following["inventory"])
            for index, item in enumerate(page["items"]):
                item["letter"] = LETTERS[index]
            page["stock_num"] = len(page["items"])

    def reply(self, raw, key):
        """DECLARED CONSTRUCTED: the engine's reply to the posted key."""
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["messages"] = []
        following["store"] = None
        here = (raw["player"]["y"], raw["player"]["x"])
        store = raw.get("store")
        entering = key.startswith("5") and store is None and here in self.cells
        page = store if store is not None else (
            self.pages.get(self.cells[here]) if entering else None)
        body = key[1:] if entering else key
        if page is not None and page["store_type"] == STORE_HOME and body[:1] and body[0] in "dp":
            self.home_reply(following, self.pages[STORE_HOME], body)
        elif page is not None and body.startswith("p"):
            letter, quantity = re.match(r"p([a-z])(\d*)", body).groups()
            shelf = self.pages[page["store_type"]]
            ware = next(it for it in shelf["items"] if it["letter"] == letter)
            count = int(quantity or 1)
            bought = dict(ware, count=count)
            bought.pop("letter")
            bought.pop("price")
            following["inventory"].append(bought)
            following["player"]["gold"] -= ware["price"] * count
            ware["count"] -= count
            self.relabel(following["inventory"])
            self.events.append(("buy", ware["name"]))
            if (ware["tval"], ware["sval"]) == (TVAL_STAFF, SV_STAFF_IDENTIFY):
                self.after_staff(following)
        elif entering and not body:
            following["store"] = page
        elif key in DIRECTIONS:
            dy, dx = DIRECTIONS[key]
            following["player"]["y"], following["player"]["x"] = here[0] + dy, here[1] + dx
            following["store"] = self.pages.get(self.cells.get((here[0] + dy, here[1] + dx)))
        elif key.startswith("\x1b`n") and key[3] in TOWN_TRAVEL_STORE_SYMBOLS:
            target = TOWN_TRAVEL_STORE_SYMBOLS.index(key[3])
            following["player"]["y"], following["player"]["x"] = self.entrance[target]
            following["store"] = self.pages.get(target)
        elif key.startswith("R"):
            following["turn"] += 2928  # an R300 rest at normal speed
        elif re.fullmatch(r"q[a-z]", key):
            potion = next(it for it in following["inventory"] if it["slot"] == key[1])
            potion["count"] -= 1
            following["inventory"] = [it for it in following["inventory"] if it["count"]]
            self.relabel(following["inventory"])
            for stat in following["player"]["stats"].values():
                if stat["drained"]:
                    stat["drained"], stat["use"] = False, stat["top"]
        elif re.match(r"r[a-z][a-z]", key) and store is None:
            scroll = next(it for it in following["inventory"] if it["slot"] == key[1])
            target = next(it for it in following["inventory"] if it["slot"] == key[2])
            if scroll["sval"] == 13:  # *Identify*
                target["fully_known"] = target["known"] = True
                self.events.append(("identify", target["name"]))
            scroll["count"] -= 1
            following["inventory"] = [it for it in following["inventory"] if it["count"]]
            self.relabel(following["inventory"])
        return following

    def after_staff(self, following):
        """Hook for the second test's constructed identification source."""

    # ------------------------------------------------------------ posting
    def execute(self, policy, raw, key, following, screens, states, expected):
        game = executor_harness.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.jsonl = [copy.deepcopy(raw)]
        game.screen = (self.shelf_screen(raw) if raw.get("store")
                       else executor_harness.command_screen(raw["turn"]))
        game.screens = screens + [self.shelf_screen(following) if following.get("store")
                                  else executor_harness.command_screen(following["turn"])]
        game.states = [copy.deepcopy(state) for state in states] + [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, "unid-deposit", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 10,
            poll_interval=0, prompt_japanese=True,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(raw, policy._monrace_knowledge),
            posting_contract=PostingContract(), in_store=bool(raw.get("store")))
        self.assertTrue(sent, (key, getattr(port.last_result, "reason", None), game.accepted))
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(game.accepted, expected, key)
        policy.confirm_key_posted(key)

    def post(self, policy, raw, key, following):
        """DECLARED CONSTRUCTED: the screens the game draws for each step."""
        here = (raw["player"]["y"], raw["player"]["x"])
        store = raw.get("store")
        home_entry = key.startswith("5") and store is None and self.cells.get(here) == STORE_HOME
        if key.startswith("~9") and store is None:
            # Recorded live screens of the ~9 Home list (knowledge menu,
            # its viewer, the menu again) answer the observed plan.
            live = Path(__file__).with_name("fixtures") / "live-screens"
            menu, viewer = (json.loads((live / name).read_text(encoding="utf-8"))["result"]
                            for name in ("27-knowledge-menu-after-viewer-esc-20260915.json",
                                         "26-knowledge-viewer-stuck-20260915-0534.json"))
            return self.execute(policy, raw, key, following, [menu, viewer, menu],
                                [raw] * 3, ["~", "9", "\x1b", "\x1b"])
        if policy.peek_staged_prompt_chain() is not None:
            # DECLARED: a prompt-gated chain (the launcher enchant) is released
            # only through the control client, which this harness does not
            # run; its key is confirmed with the constructed reply.
            policy.confirm_key_posted(key)
            return None
        if policy.last_reason.startswith("home-errand:"):
            # The Home errand posts its entry and tail as one atomic command.
            return self.execute(policy, raw, key, following, [], [], [key])
        if store is not None and store["store_type"] == STORE_HOME and key[:1] == "d":
            # The Home page interprets its observed atomic deposit tail whole.
            return self.execute(policy, raw, key, following, [], [], [key])
        if home_entry and len(key) > 1:
            inside = dict(copy.deepcopy(raw), store=self.pages[STORE_HOME])
            screens, expected = [self.shelf_screen(inside)], ["5"]
            for command, letter, quantity in re.findall(r"([dp])([a-zA-Z])(?:(\d+\r))?", key[1:]):
                prompt = ("どのアイテムを置きますか?" if command == "d"
                          else "どのアイテムを取りますか? ")
                head = "持ち物" if command == "d" else "アイテム"
                screens.append(executor_harness.prompt_screen(f"({head}:a-z, ESCで中断) {prompt}"))
                expected += [command, letter]
                if quantity:
                    screens.append(executor_harness.prompt_screen("いくつですか (1-99): 1"))
                    expected.append(quantity)
                screens.append(self.shelf_screen(inside))
            expected.append("\x1b")
            return self.execute(policy, raw, key, following, screens,
                                [inside] * len(screens), expected)
        if store is not None and re.fullmatch(r"p[a-z]\d*\r\r?", key):
            ware = next(it for it in store["items"] if it["letter"] == key[1])
            quantity = re.match(r"p[a-z](\d*)", key).group(1)
            # store.cpp:181-185 and its purchase prompts.
            screens = [executor_harness.prompt_screen(
                f"(商品:a-{store['items'][-1]['letter']}, ESCで中断) どの品物が欲しいんだい? ")]
            expected = ["p", key[1]]
            if quantity:
                screens.append(executor_harness.prompt_screen(f"いくつですか (1-{ware['count']}): 1"))
                expected.append(quantity + "\r")
            screens.append(executor_harness.prompt_screen(
                f"買値 ${ware['price'] * int(quantity or 1)} で買いますか？[Y/n]"))
            expected.append("\r")
            return self.execute(policy, raw, key, following, screens,
                                [raw] * len(screens), expected)
        if re.match(r"r[a-z][a-z]", key) and store is None:
            target = ("どのアイテムを*鑑定*しますか?" if policy.last_reason.startswith("identify:")
                      else "どのアイテムを強化しますか?")
            screens = [
                executor_harness.prompt_screen("(持ち物:a-z, ESCで中断) どの巻物を読みますか?"),
                executor_harness.prompt_screen(f"(持ち物:a-z, ESCで中断) {target}"),
            ]
            return self.execute(policy, raw, key, following, screens, [raw, raw],
                                # The *Identify* result pages' Escapes are
                                # released only at observed result screens.
                                ["r", key[1], key[2]])
        if key.startswith("R"):
            # cmd-move.cpp:446 asks the rest count.
            screens = [executor_harness.prompt_screen(
                "休憩 (0-9999, '*' で HP/MP全快, '&' で必要なだけ): &")]
            return self.execute(policy, raw, key, following, screens, [raw], ["R", key[1:]])
        if re.fullmatch(r"q[a-z]", key):
            screens = [executor_harness.prompt_screen("(持ち物:a-z, ESCで中断) どの薬を飲みますか?")]
            return self.execute(policy, raw, key, following, screens, [raw], ["q", key[1]])
        return self.shop_post(policy, raw, key, following)

    def drive(self, policy, raw, *, limit, done):
        reasons = []
        for _ in range(limit):
            board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            board = policy.with_known_skill_exp(board)
            policy.observe_store_screen(board.store is not None)
            key, reason = str(policy.choose_key(board)), policy.last_reason
            reasons.append(reason)
            if done(reason, key):
                return raw, reasons
            self.assertFalse(reason.startswith("town:blocked:"), reasons[-8:])
            self.assertTrue(key, reasons[-8:])
            following = self.reply(raw, key)
            with self.subTest(step=len(reasons), reason=reason, key=key):
                self.post(policy, raw, key, following)
            raw = following
            if key.startswith("~9"):
                # DECLARED CONSTRUCTED: the ~9 Home list of the current shelf.
                answer = copy.deepcopy(self.case["home_answer"])
                answer["turn"] = raw["turn"]
                answer["knowledge"]["items"] = [
                    {k: v for k, v in item.items() if k != "letter"}
                    for item in self.pages[STORE_HOME]["items"]]
                self.consume(policy, answer)
        self.fail(("no departure", self.events, reasons[-12:]))

    # ------------------------------------------------------------ tests
    def test_recorded_stop(self):
        decision = self.case["decision"]
        self.assertEqual((decision["turn"], decision["reason"]),
                         (406215, "town:blocked:departure-unsatisfiable"))
        self.assertEqual(decision["departure_block"]["failed"], ["identify_staff_ready"])
        self.assertEqual(decision["shop_selector"]["pack_refusal"], "full-pack-nonstacking")
        self.assertEqual(decision["inventory"], {"used": 19, "free": 4})
        policy, raw = self.boundary()
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        waiting = [item.name for item in board.inventory
                   if item.is_equipment and policy._identification_flow_candidate(item)]
        self.assertEqual([name.startswith(WAITING) for name in waiting], [True] * 4)
        self.assertTrue(all(policy._identification_source_obtainability(board, full=True)
                            == "unavailable" for _ in waiting))

    def test_waiting_equipment_is_shelved_and_the_staff_bought(self):
        policy, raw = self.boundary()
        raw, reasons = self.drive(policy, raw, limit=60,
                                  done=lambda reason, key: reason.startswith(DEPARTURE))
        deposited = [name for kind, name in self.events if kind == "deposit"]
        self.assertEqual(sorted(name.startswith(WAITING) for name in deposited), [True] * 4)
        bought = [name for kind, name in self.events if kind == "buy"]
        self.assertIn("鑑定の杖 (3x 16回分)", bought)
        self.assertLess(self.events.index(("deposit", deposited[-1])),
                        self.events.index(("buy", "鑑定の杖 (3x 16回分)")))
        # Nothing is taken back without an identification source.
        self.assertNotIn("withdraw", [kind for kind, _ in self.events])
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertTrue(policy._identify_staff_ready(board))

    def test_shelved_equipment_is_taken_back_and_identified_with_a_source(self):
        def star_identify(following):
            # DECLARED CONSTRUCTED: four *Identify* scrolls arrive with the
            # staff (the Alchemist's recorded page of this visit had none).
            scroll = {"name": "*鑑定*の巻物", "count": 4, "tval": 70, "sval": 13,
                      "aware": True, "known": True, "fully_known": True,
                      "is_equipment": False, "weight": 5}
            template = next(it for it in following["inventory"] if it["tval"] == 70)
            following["inventory"].append(dict(template, **scroll))
            self.relabel(following["inventory"])

        self.after_staff = star_identify
        policy, raw = self.boundary()
        raw, reasons = self.drive(policy, raw, limit=80,
                                  done=lambda reason, key: reason.startswith(DEPARTURE))
        kinds = [kind for kind, _ in self.events]
        self.assertIn("withdraw", kinds)
        withdrawn = next(name for kind, name in self.events if kind == "withdraw")
        self.assertTrue(withdrawn.startswith(WAITING), withdrawn)
        self.assertEqual(self.events[kinds.index("withdraw") + 1], ("identify", withdrawn))
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertGreaterEqual(23 - len(board.inventory), 4)


if __name__ == "__main__":
    import unittest
    unittest.main()
