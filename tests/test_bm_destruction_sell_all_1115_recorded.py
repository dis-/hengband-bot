"""The Black Market's Staff of *Destruction* bought in the visit that saw it (owner 2026-11-15).

Owner 2026-11-15: 「破壊の杖は最優先で購入、所持金が足りなければ自宅の予備の装備を
アーティファクト以外全て売ってでも購入する。以前決めた通りである。」, 「念のため確認するが、
すべて売るのは武器と胴防具だけ」 and 「闇市で破壊の杖を見て所持金が足りない→予備装備売却
処理→購入→出発　がただしい。その訪問中に購入まで遂行する必要がある。」

Recorded: n1-c life-214's town visit of 2026-11-15 17:45 (Magic-Eater Lv40, the Outpost,
build bot-d89dedaff; tests/extract_bm_destruction_sell_all_1115_fixture.py).  Journal row 27
is the visit's Black Market page: a *破壊*の杖 (4回分) at 70,297 with 76,060 gold, 581 short
of it under the optional reserve (6,344).  Live, the visit bought a Wand of Stone to Mud
(row 29, 3,011) and a Staff of Speed (row 49, 27,617) on that page, sold nothing for the
staff and left for Morivant (row 50) without it.

The rows up to the page replay through the public chooser and the live CLI's
owner-retirement entrance (--owner-retired-log-only, as the viewing bots run), each
posting its recorded key.  DECLARED WALL: rows 11-17 are posted as recorded although the
replay decides them differently (on main as well: live, the ware taken out at row 10 was
held by another owner, ``home:full-skip:sale-item-held``; the restored policy does not
reproduce that hold); rows 0-10 and 18-27 decide as recorded.

DECLARED CONSTRUCTED from row 28 on: the boards after the policy's own keys come from a
minimal town world (``TownWorld``) built from the recorded boards: the Black Market page of
row 27, the Home page of row 37, the Home census of row 36 and the store entrances of the
recorded grid map.  A walk or native travel lands on its store's entrance (and enters it),
an atomic Home take moves the ware to the pack with the game's 「…を取った。」 receipt, an
inscription adds its tag to the name, a sale pays ``bm_destruction_fund.sale_estimate`` of
the piece (the fund's own lower bound) with the game's 「…を $N で売却しました。」 receipt,
a purchase pays the shelf price with its receipt.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
from dataclasses import replace
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hengbot import bm_destruction_fund, item_fate
from hengbot.cli import _consume_response_sequence, _handle_owner_retirement
from hengbot.model import STORE_BLACK, STORE_HOME, parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "bm-destruction-sell-all-1115" / "n1c-214-1745"
LOG_ONLY = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
BLACK_MARKET_ROW = 27
CENSUS_ROW = 36
HOME_PAGE_ROW = 37
# Rows the replay decides as the live process did (see the module docstring).
MATCHED_ROWS = (*range(0, 11), *range(18, BLACK_MARKET_ROW + 1))
PRICE = 70297
GOLD = 76060
RESERVE = 6344
STAFF_LETTER = "J"
# The recorded store entrances (grid map ``s`` cells): store type -> (x, y).
ENTRANCES = {0: (119, 31), 1: (105, 32), 2: (91, 31), 3: (77, 31), 4: (91, 37),
             5: (106, 38), 6: (84, 45), 7: (123, 45), 8: (81, 38), 9: (97, 44)}
STEPS = {"1": (-1, 1), "2": (0, 1), "3": (1, 1), "4": (-1, 0), "5": (0, 0),
         "6": (1, 0), "7": (-1, -1), "8": (0, -1), "9": (1, -1)}
LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
LEAVING_TOWN = ("me-staff:travel", "town:recall", "town:wait-recall", "town:descend")


def post(policy, board, key, visit_before):
    """Post ``key`` as the live CLI does; returns what was posted."""
    key = policy.validate_read_key(board, key)
    key = _handle_owner_retirement(LOG_ONLY, board, key, policy, visit_before)
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
    return key


class TownWorld:
    """DECLARED CONSTRUCTED: the boards after the policy's own keys (module docstring)."""

    def __init__(self, policy, board, home, pages, census, ledger):
        self.policy = policy
        self.cur = board
        self.home = home
        self.pages = pages
        self.census = census
        self.ledger = ledger
        self.turn = board["turn"]
        self.inputs = []
        self.log = []

    def _tick(self, raw, messages=()):
        self.turn += 10
        raw["turn"] = self.turn
        raw["messages"] = list(messages)
        raw["type"] = "store" if raw.get("store") else "player_turn"
        return raw

    @staticmethod
    def _at(raw, position):
        raw["player"] = dict(raw["player"], x=position[0], y=position[1])

    def _outside(self, messages=()):
        raw = copy.deepcopy(self.cur)
        raw["store"] = None
        return self._tick(raw, messages)

    def _page(self, store_type):
        raw = copy.deepcopy(self.cur)
        self._at(raw, ENTRANCES[store_type])
        if store_type == STORE_HOME:
            page = copy.deepcopy(self.pages[STORE_HOME])
            page["items"] = [dict(item, letter=LETTERS[index])
                             for index, item in enumerate(self.home[:page["page_size"]])]
            page["stock_num"] = len(self.home)
        else:
            page = copy.deepcopy(self.pages.get(store_type) or {
                "store_type": store_type, "items": [], "page_size": 52, "page_top": 0,
                "stock_num": 0, "capacity": 24, "max_cost": 30000})
        raw["store"] = page
        return self._tick(raw)

    @staticmethod
    def _repack(raw, added=None):
        pack = [dict(item) for item in raw["inventory"]]
        if added is not None:
            pack.append(dict(added))
        pack.sort(key=lambda item: (-item["tval"], item["sval"]))
        for index, item in enumerate(pack):
            item["slot"] = LETTERS[index]
            item.pop("letter", None)
            item.pop("price", None)
        raw["inventory"] = pack
        return None if added is None else next(item for item in pack if item["name"] == added["name"])

    def board(self):
        return parse_snapshot(self.cur, self.policy._monrace_knowledge)

    def apply(self, key):
        cur = self.cur
        store = (cur.get("store") or {}).get("store_type")
        travel = re.fullmatch(r"\x1b?`n(.)\.", key)
        if travel:
            self.cur = self._page(ord(travel.group(1)) - ord("!"))
            return
        if key in STEPS and store is None:
            dx, dy = STEPS[key]
            position = (cur["player"]["x"] + dx, cur["player"]["y"] + dy)
            entered = next((kind for kind, cell in ENTRANCES.items() if cell == position), None)
            self._at(cur, position)
            self.cur = self._page(entered) if entered is not None else self._tick(copy.deepcopy(cur))
            return
        if key == "Cf\ry\x1b\x1b":
            self.policy._periodic_dump_requested = False
            self.cur = self._tick(copy.deepcopy(cur))
            return
        if key in ("~9\x1b\x1b", "~9\x1b"):
            line = copy.deepcopy(self.census)
            for field in ("inventory", "equipment", "player"):
                line[field] = cur[field]
            line["turn"] = self.turn
            line["knowledge"] = dict(line["knowledge"], items=copy.deepcopy(self.home))
            self.inputs.append(json.dumps(line, ensure_ascii=False))
            self.cur = self._tick(copy.deepcopy(cur))
            return
        if store is not None and key == "\x1b":
            self.cur = self._outside()
            return
        take = re.fullmatch(r"5( *)p([A-Za-z])\x1b", key)
        if take and store is None:
            index = len(take.group(1)) * self.pages[STORE_HOME]["page_size"] + LETTERS.index(take.group(2))
            ware = self.home.pop(index)
            if ware["count"] > 1:
                self.home.insert(index, dict(ware, count=ware["count"] - 1))
            raw = self._outside()
            row = self._repack(raw, dict(ware, count=1))
            raw["messages"] = [f"{row['name']}({row['slot']})を取った。"]
            self.cur = raw
            self.log.append(("take", row["name"]))
            return
        inscribe = re.fullmatch(r"\{([a-zA-Z])@(\d)\r", key)
        if inscribe and store is not None:
            raw = copy.deepcopy(cur)
            tag = "@" + inscribe.group(2)
            for item in raw["inventory"]:
                if item["slot"] == inscribe.group(1):
                    item["inscription"] = tag
                    item["name"] = (item["name"][:-1] + ", " + tag + "}" if item["name"].endswith("}")
                                    else item["name"] + " {" + tag + "}")
            self.cur = self._tick(raw)
            return
        sale = re.fullmatch(r"d([a-zA-Z0-9])(\d*)\r?y?\r?", key)
        if sale and store is not None and store != STORE_HOME:
            letter = sale.group(1)
            raw = copy.deepcopy(cur)
            row = next(item for item in raw["inventory"]
                       if (item.get("inscription") == "@" + letter if letter.isdigit()
                           else item["slot"] == letter))
            carried = next(item for item in self.board().inventory if item.slot == row["slot"])
            price = bm_destruction_fund.sale_estimate(self.policy, carried)
            raw["inventory"] = [item for item in raw["inventory"] if item is not row]
            self._repack(raw)
            raw["player"] = dict(raw["player"], gold=raw["player"]["gold"] + price)
            self.cur = self._tick(raw, [f"{row['name']}を ${price}で売却しました。"])
            self.log.append(("sell", row["name"], price))
            return
        buy = re.fullmatch(r"p([A-Za-z])(\d*)\r*\x1b?", key)
        if buy and store is not None and store != STORE_HOME:
            letter, quantity = buy.group(1), int(buy.group(2) or 1)
            raw = copy.deepcopy(cur)
            ware = next(item for item in raw["store"]["items"] if item["letter"] == letter)
            raw["player"] = dict(raw["player"], gold=raw["player"]["gold"] - ware["price"] * quantity)
            row = self._repack(raw, dict(ware, count=quantity))
            wares = [item for item in raw["store"]["items"] if item is not ware]
            if ware["count"] > quantity:
                wares.insert(raw["store"]["items"].index(ware), dict(ware, count=ware["count"] - quantity))
            raw["store"]["items"] = wares
            self.pages[store] = raw["store"]
            messages = [f"{ware['name']}を ${ware['price']}で購入しました。",
                        f"{row['name']}({row['slot']})を手に入れた。"]
            if key.endswith("\x1b"):
                raw["store"] = None
            self.cur = self._tick(raw, messages)
            self.log.append(("buy", store, ware["name"], ware["price"] * quantity))
            return
        raise AssertionError(f"the constructed town has no effect for {key!r} (store {store})")

    def decide(self):
        """Deliver the pending responses and the board; decide and post its key."""
        lines = [*self.inputs, json.dumps(self.cur, ensure_ascii=False)]
        self.inputs = []
        _consume_response_sequence([line + "\n" for line in lines], self.policy, lambda _key: True,
                                   self.policy._monrace_knowledge, parse_snapshots=False,
                                   knowledge_ledger_path=self.ledger)
        self.policy.observe_store_screen(True if self.cur.get("store") else None)
        board = self.board()
        before = copy.copy(self.policy._store_visit)
        key = self.policy.choose_key(board)
        reason = self.policy.last_reason
        return board, key, reason, before


class BlackMarketDestructionSellAll1115RecordedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def to_black_market(self, price=PRICE):
        """Rows 0-27 posted as recorded; returns the policy, the journal and row 27's board."""
        policy, recorded, steps = load(FIXTURE, self.scratch)
        for row, supply in steps[:BLACK_MARKET_ROW]:
            board = supply()
            before = copy.copy(policy._store_visit)
            key = policy.choose_key(board)
            entry = recorded[row["row"]]
            if row["row"] in MATCHED_ROWS:
                self.assertEqual((key, policy.last_reason), (entry["key"], entry["reason"]), row["row"])
            post(policy, board, entry["key"], before)
        board = steps[BLACK_MARKET_ROW][1]()
        if price != PRICE:
            # DECLARED CONSTRUCTED: the staff at another price on the recorded page.
            board = parse_snapshot(self.priced(recorded, price), policy._monrace_knowledge)
        return policy, recorded, board

    @staticmethod
    def raw(recorded, row):
        return json.loads(recorded[row]["line"])

    def priced(self, recorded, price):
        raw = self.raw(recorded, BLACK_MARKET_ROW)
        for ware in raw["store"]["items"]:
            if ware["letter"] == STAFF_LETTER:
                ware["price"] = price
        return raw

    def world(self, policy, recorded, black_market_page):
        census = next(json.loads(line) for line in recorded[CENSUS_ROW]["inputs"]
                      if json.loads(line).get("type") == "knowledge")
        pages = {STORE_BLACK: black_market_page, STORE_HOME: self.raw(recorded, HOME_PAGE_ROW)["store"]}
        return TownWorld(policy, self.raw(recorded, BLACK_MARKET_ROW + 1),
                         copy.deepcopy(census["knowledge"]["items"]), pages, census,
                         self.scratch / "knowledge.jsonl")

    def leave_black_market(self, policy, recorded, board):
        """Row 27, the Black Market page: nothing else is bought before the staff."""
        self.assertEqual(policy._full_departure_resupply_reserve(board), RESERVE)
        self.assertEqual(board.player.gold, GOLD)
        staff = next(ware for ware in board.store.items if ware.letter == STAFF_LETTER)
        self.assertTrue(policy._is_destruction_staff(staff))
        before = copy.copy(policy._store_visit)
        key = policy.choose_key(board)
        entry = recorded[BLACK_MARKET_ROW]
        self.assertEqual((key, policy.last_reason), (entry["key"], entry["reason"]))
        # Live (rows 29 and 49): the Wand of Stone to Mud as the optional pick, then the
        # Staff of Speed of the Magic-Eater staff sequence.  Now the staff owns the page.
        self.assertTrue(bm_destruction_fund.staff_pending(policy, board))
        self.assertIsNone(policy._black_market_optional_purchase(board))
        self.assertIsNone(policy._next_purchase(board))
        self.assertTrue(policy._bm_destruction_shelf["withheld"])
        post(policy, board, entry["key"], before)

    def test_the_visit_sells_spares_buys_the_staff_and_then_departs(self):
        policy, recorded, board = self.to_black_market()
        shortfall = PRICE + RESERVE - GOLD
        self.leave_black_market(policy, recorded, board)
        self.assertEqual(bm_destruction_fund.shortfall(policy, board), shortfall)
        world = self.world(policy, recorded, self.raw(recorded, BLACK_MARKET_ROW)["store"])
        decisions, funded, bought_at = [], [], None
        for _ in range(100):
            board, key, reason, before = world.decide()
            decisions.append((key, reason))
            if bought_at is None:
                # Until the purchase: the departure waits, and so do the class
                # sequences that leave town (the Magic-Eater staff trip of row 50).
                self.assertFalse(policy._town_departure_conjuncts(board, commit=False)
                                 ["destruction_staff_settled"], decisions)
                self.assertTrue(bm_destruction_fund.holds_town_for_staff(policy, board)
                                or board.store is not None)
                self.assertFalse(reason.startswith(LEAVING_TOWN), decisions)
                if reason == "home-errand:atomic-withdraw:full-home-sale":
                    # The take is the fund's piece (its plan, read in this decision).
                    funded.append(policy._home_full_relief.get("fund"))
            if reason.startswith(LEAVING_TOWN):
                break
            posted = post(policy, board, key, before)
            if posted:
                world.apply(posted)
            if bought_at is None and any(entry[0] == "buy" for entry in world.log):
                bought_at = len(decisions)
        else:
            self.fail(f"the visit did not leave town: {decisions[-8:]} {world.log} {bought_at}")
        # The census came first, then Home's spares: a weapon or body armour (or a
        # launcher, 2026-11-07), no artifact; one piece covers the 581.
        self.assertIn(("~9", "home:request-knowledge-scan"), decisions[:3])
        self.assertTrue(funded)
        self.assertNotIn(None, funded)
        self.assertEqual({item_fate.SLOT_BY_TVAL[signature[1]] for signature in funded}
                         - bm_destruction_fund.FUND_SLOTS, set())
        self.assertFalse(any(signature[0].startswith(("★", "☆")) for signature in funded))
        takes = [entry for entry in world.log if entry[0] == "take"]
        sales = [entry for entry in world.log if entry[0] == "sell"]
        buys = [entry for entry in world.log if entry[0] == "buy"]
        self.assertEqual(takes[0][1], funded[0][0])
        self.assertGreaterEqual(sales[0][2], shortfall)
        # The first purchase of the visit after the page is the staff, at its price,
        # after the sale; live, the Wand of Stone to Mud and the Staff of Speed came first.
        self.assertEqual(buys[0], ("buy", STORE_BLACK, "*破壊*の杖 (4回分)", PRICE))
        self.assertLess(world.log.index(sales[0]), world.log.index(buys[0]))
        # Then the departure: the staff is carried, nothing is left for it.
        board = world.board()
        self.assertTrue(any(policy._is_destruction_staff(item) for item in board.inventory))
        self.assertFalse(bm_destruction_fund.staff_pending(policy, board))
        self.assertEqual(policy._bm_destruction_shelf["closed"], "bought")
        self.assertTrue(policy._town_departure_conjuncts(board, commit=False)["destruction_staff_settled"])
        self.assertTrue(reason.startswith(LEAVING_TOWN), reason)
        # The fund sold nothing after the purchase: what Home sold then is the
        # ordinary junk sweep's (at most SWEEP_LIMIT_PER_STAY wares a stay).
        after = world.log[world.log.index(buys[0]) + 1:]
        self.assertLessEqual(sum(entry[0] == "sell" for entry in after), item_fate.SWEEP_LIMIT_PER_STAY)
        # The departure here is live row 50's: the Magic-Eater staff trip to Morivant.
        self.assertTrue(reason.startswith("me-staff:travel"), reason)
        leaving = copy.deepcopy(policy)
        self.assertEqual(leaving._opening_q34_town_key(board, []), key)
        # DECLARED CONSTRUCTED: the same board with a second staff still pending on
        # this stay's shelf (at 1 gold, so covered): the trip waits for it.
        waiting = copy.deepcopy(policy)
        waiting._bm_destruction_shelf = dict(waiting._bm_destruction_shelf, price=1,
                                              carried=bm_destruction_fund._carried(waiting, board))
        waiting._bm_destruction_shelf.pop("closed")
        self.assertTrue(bm_destruction_fund.holds_town_for_staff(waiting, board))
        self.assertIsNone(waiting._opening_q34_town_key(board, []))
        self.assertFalse(waiting._town_departure_conjuncts(board, commit=False)["destruction_staff_settled"])

    def test_every_rank_of_a_spare_weapon_or_body_armour_but_no_artifact(self):
        policy, recorded, board = self.to_black_market()
        self.leave_black_market(policy, recorded, board)
        world = self.world(policy, recorded, self.raw(recorded, BLACK_MARKET_ROW)["store"])
        for _ in range(3):
            board, key, reason, before = world.decide()
            if policy._home_knowledge_current:
                break
            world.apply(post(policy, board, key, before))
        self.assertTrue(policy._home_knowledge_current)
        # DECLARED CONSTRUCTED: the same board 380,000 poorer, so far short (380,581)
        # that the fund reaches into Home's best spares: every eligible piece's
        # estimate together is 392,267, ranks 2+ alone 364,947.
        poorer = replace(board, player=replace(board.player, gold=board.player.gold - 380000))
        plan = bm_destruction_fund.plan(policy, poorer)
        self.assertTrue(plan)
        items = {policy._item_signature(item): item for item in policy._home_knowledge_items}
        chosen = [items[signature] for signature in plan]
        self.assertEqual({item_fate.SLOT_BY_TVAL[item.tval] for item in chosen}
                         - bm_destruction_fund.FUND_SLOTS, set())
        self.assertFalse(any(item.is_artifact or not item.known for item in chosen))
        # 「2〜10位も」「アーティファクト以外全て」: rank 1 of a slot is in as well when it is spare.
        ranks = {item_fate.gear_rank(policy, poorer, item) for item in chosen}
        self.assertIn(1, ranks)
        self.assertIn("ゴールドドラゴン・スケイルメイル (-2) [40,+15] {r轟}",
                      {item.name for item in chosen if item_fate.gear_rank(policy, poorer, item) == 1})
        # Home's artifacts of these slots stay, and no ring, amulet or armour of another slot.
        artifacts = [item for item in policy._home_knowledge_items
                     if item.is_artifact and item_fate.SLOT_BY_TVAL.get(item.tval) in bm_destruction_fund.FUND_SLOTS]
        self.assertTrue(artifacts)
        self.assertFalse(any(policy._item_signature(item) in plan for item in artifacts))

    def test_spares_short_of_the_staff_sell_nothing_and_say_so(self):
        # DECLARED CONSTRUCTED: the staff at 9,000,000 on the recorded page.
        price = 9000000
        policy, recorded, board = self.to_black_market(price)
        before = copy.copy(policy._store_visit)
        key = policy.choose_key(board)
        self.assertTrue(bm_destruction_fund.staff_pending(policy, board))
        post(policy, board, key, before)
        world = self.world(policy, recorded, self.priced(recorded, price)["store"])
        world.cur = self.raw(recorded, BLACK_MARKET_ROW + 1)
        decisions = []
        for _ in range(6):
            board, key, reason, before = world.decide()
            decisions.append((key, reason))
            if policy._home_knowledge_current:
                break
            world.apply(post(policy, board, key, before))
        self.assertTrue(policy._home_knowledge_current)
        self.assertEqual(bm_destruction_fund.plan(policy, board), ())
        # The next board closes the errand and says so in the decision log.
        posted = post(policy, board, key, before)
        world.apply(posted)
        board, key, reason, before = world.decide()
        self.assertFalse(bm_destruction_fund.staff_pending(policy, board))
        self.assertEqual(policy._bm_destruction_shelf["closed"], "unaffordable")
        self.assertTrue(any(warning.startswith(bm_destruction_fund.UNAFFORDABLE_WARNING)
                            for warning in policy._town_visit_ledger.drift_warnings))
        self.assertTrue(policy._town_departure_conjuncts(board, commit=False)["destruction_staff_settled"])
        # Nothing of Home was taken out for it.
        self.assertIsNone((policy._home_full_relief or {}).get("fund"))
        self.assertFalse(any(entry[0] == "take" for entry in world.log))


if __name__ == "__main__":
    unittest.main()
