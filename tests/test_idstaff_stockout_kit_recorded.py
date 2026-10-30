"""D29: the recorded n1-b life-260 departure-unsatisfiable stops (2026-10-30 18:00).

The warrior (Lv25, 17,784 gold) carried four Identify staves of 3 charges,
12 of the 20 a 10F+ departure needs; the Magic shop sold only 1-3 charge
staves, so no purchase could reach the target.  The Identify-staff stockout
time-pass (one Yeek cave mining run, then Home and Magic again) was installed
(``town:identify-staff-stockout-mining``, fundraising ``prepare``) but its
mining kit lacked the one Treasure Detection scroll.  Above the 15,000-gold
fundraising target the kit's town needs were not produced (only the recall
stockout time-pass and the supply stockout were exempt), so the run neither
fetched the scroll Home holds nor left town.  After the Magic restock wait the
departure terminal stopped with departure_block.failed ["identify_staff_ready"]
three times and retired the character.

The test starts on the restarted process's first board (turn 729490), feeds
every recorded ring row through the production response consumer and decides
on the recorded decision boards with the public chooser.  From the board where
the recorded process waited for the Magic restock, replies to newly posted
keys are constructed (marked below) and every key goes through the production
executor.  Fixture: tests/extract_idstaff_stockout_kit_fixture.py.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import io
import json
from pathlib import Path
import tempfile
import time

from hengbot.cli import (
    PostingContract, _ExecutorInputPort, _consume_response_sequence, _request_due_dump,
    _send_decision_key_with_prompt_chain,
)
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import TOWN_TRAVEL_STORE_SYMBOLS
from tests import test_lv7_town_stop_recorded as lv7
from tests.test_esp_threat_rest_recorded import EDIT, _policy
import tests.test_input_executor as executor_harness


FIXTURE = Path(__file__).with_name("fixtures") / "idstaff-stockout-kit-20261030.json.gz"
DIRECTIONS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
              "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}
# The decision board on which the recorded process waited for the Magic
# restock (``town:wait-restock:magic``) instead of fetching its kit.
KIT_BOARD = 10


class IdstaffStockoutKitRecordedTest(executor_harness.ProductionHarness):
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)
    shop_post = lv7.Lv7TownStopRecordedTest.post

    def post(self, policy, raw, key, following):
        if policy.last_reason == "home:atomic-withdraw":
            # DECLARED CONSTRUCTED: the Home screens of store.cpp for "5"
            # (enter on the entrance), "p" (get), the letter, the quantity
            # and Escape.
            cells = {(y, x): store for y, x, store in self.case["store_cells"]}
            page = self.pages[str(cells[(raw["player"]["y"], raw["player"]["x"])])]
            inside = dict(copy.deepcopy(raw), store=page)
            letter, quantity = key[2], key[3:].removesuffix("\r\x1b")
            ware = next(item for item in page["items"] if item["letter"] == letter)
            screens = [
                self.shelf_screen(inside),
                # store.cpp:181-185 (the Home chooser on this page's letters).
                executor_harness.prompt_screen(
                    f"(アイテム:a-{page['items'][-1]['letter']}, ESCで中断) どのアイテムを取りますか? "),
                executor_harness.prompt_screen(f"いくつですか (1-{ware['count']}): 1"),
                self.shelf_screen(inside),
            ]
            states = [inside] * len(screens)
            expected = ["5", "p", letter, quantity + "\r", "\x1b"]
        elif key.startswith("R"):
            # DECLARED CONSTRUCTED: cmd-move.cpp:446 asks the rest count.
            screens = [executor_harness.prompt_screen(
                "休憩 (0-9999, '*' で HP/MP全快, '&' で必要なだけ): &")]
            states = [raw]
            expected = ["R", key[1:]]
        else:
            return self.shop_post(policy, raw, key, following)
        game = executor_harness.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.jsonl = [copy.deepcopy(raw)]
        game.screen = executor_harness.command_screen(raw["turn"])
        game.screens = screens + [executor_harness.command_screen(following["turn"])]
        game.states = [copy.deepcopy(state) for state in states] + [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, "idstaff-stockout-kit", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 10,
            poll_interval=0, prompt_japanese=True,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(raw, policy._monrace_knowledge),
            posting_contract=PostingContract(), in_store=False)
        self.assertTrue(sent, (getattr(port.last_result, "reason", None), game.accepted))
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(game.accepted, expected)
        policy.confirm_key_posted(key)

    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        super().setUp()
        self.directory = Path(tempfile.mkdtemp())

    def replay(self, through):
        """Decide on the recorded boards 0..through; return the last key."""
        policy = _policy(self.directory, self.monrace)
        # The viewing bots run with these startup flags (bot-stderr.log).
        policy._crossarea_fundraising_enforced = True
        policy._in_store_ops_enabled = True
        _request_due_dump(policy, 0, 0)
        rows, boards = self.case["rows"], self.case["decision_rows"]
        keys = []
        for index, row in enumerate(rows[: boards[through] + 1]):
            _, snapshots = _consume_response_sequence(
                [json.dumps(row, ensure_ascii=False)], policy, lambda _key: True,
                self.monrace, knowledge_ledger_path=self.directory / "knowledge.jsonl")
            if index not in boards:
                continue
            board = snapshots[-1]
            if index == 0:
                policy.prime(board)
            board = policy.with_known_skill_exp(board)
            policy.observe_store_screen(board.store is not None)
            keys.append((policy.choose_key(board), policy.last_reason))
            if index != boards[through]:
                policy.confirm_key_posted(keys[-1][0])
        return policy, copy.deepcopy(rows[boards[through]]), keys

    def reply(self, raw, key):
        """DECLARED CONSTRUCTED: the engine's reply to the posted key."""
        cells = {(y, x): store for y, x, store in self.case["store_cells"]}
        entrance = {store: (y, x) for (y, x), store in cells.items()}
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["messages"] = []
        following["store"] = None
        here = (raw["player"]["y"], raw["player"]["x"])
        body = key.removeprefix("5") if here in cells else key
        page = raw.get("store") or (self.pages.get(str(cells[here])) if here in cells else None)
        if page is not None and body.startswith("p"):
            # Home withdrawal (the recorded page's letter and quantity).
            ware = next(it for it in page["items"] if it["letter"] == body[1])
            quantity = int("".join(c for c in body[2:] if c.isdigit()) or 1)
            slots = {it["slot"] for it in following["inventory"]}
            item = dict(ware, count=quantity,
                        slot=next(c for c in "abcdefghijklmnopqrstuvw" if c not in slots))
            item.pop("letter")
            item.pop("price", None)
            following["inventory"].append(item)
            self.withdrawn.append((ware["name"], quantity))
        elif key in DIRECTIONS:
            dy, dx = DIRECTIONS[key]
            following["player"]["y"], following["player"]["x"] = here[0] + dy, here[1] + dx
            following["store"] = self.pages.get(str(cells.get((here[0] + dy, here[1] + dx))))
        elif key.startswith("\x1b`n") and key[3] in TOWN_TRAVEL_STORE_SYMBOLS:
            store = TOWN_TRAVEL_STORE_SYMBOLS.index(key[3])
            following["player"]["y"], following["player"]["x"] = entrance[store]
            following["store"] = self.pages.get(str(store))
        elif key.startswith("R"):
            following["turn"] += 2928  # the recorded R300 rest: 729922 -> 732860
        return following

    def test_recorded_suffix_reaches_the_restock_wait(self):
        recorded = self.case["decisions"]
        stop = recorded[-1]
        self.assertEqual((stop["turn"], stop["reason"]),
                         (732860, "town:blocked:departure-unsatisfiable"))
        self.assertEqual(stop["departure_block"]["failed"], ["identify_staff_ready"])
        self.assertEqual(stop["fundraising"]["mode"], "prepare")
        self.assertEqual(stop["procurement_requirements"][0],
                         {"item": "Treasure Detection scrolls", "current": 0,
                          "target": 1, "missing": 1})
        self.assertEqual(recorded[KIT_BOARD]["reason"], "town:wait-restock:magic")
        policy, raw, keys = self.replay(KIT_BOARD - 1)
        self.assertEqual(keys, [(row["key"], row["reason"]) for row in recorded[:KIT_BOARD]])
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertGreater(board.player.gold, 15000)
        self.assertEqual(policy._total_identify_staff_charges(board), 12)
        self.assertTrue(policy._identify_staff_mining_plan)

    def test_stockout_run_fetches_its_detection_and_leaves_town(self):
        policy, raw, keys = self.replay(KIT_BOARD)
        key, reason = keys[-1]
        self.pages = copy.deepcopy(self.case["pages"])
        self.withdrawn, reasons = [], [reason]
        for _ in range(40):
            self.assertFalse(reason.startswith("town:blocked:"), reasons[-8:])
            if key.startswith("\x1b`n>"):
                break
            following = self.reply(raw, key)
            self.post(policy, raw, key, following)
            raw = following
            board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            board = policy.with_known_skill_exp(board)
            policy.observe_store_screen(board.store is not None)
            key, reason = str(policy.choose_key(board)), policy.last_reason
            reasons.append(reason)
        else:
            self.fail(("no departure", reasons[-12:]))
        self.assertEqual(reason, "town:travel-entrance")
        self.assertEqual(self.withdrawn, [("財宝感知の巻物 {50%引き}", 1)])
        self.assertEqual(policy._fundraising_mode, "mine")


if __name__ == "__main__":
    import unittest
    unittest.main()
