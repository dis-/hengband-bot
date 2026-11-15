"""n1-a life-527 (2026-11-15 23:56): the one-shot composed from a shelf retired at its own release.

The new warrior (Lv7, 161 gold after selling two Q34 rewards at the Alchemist) came back to the
General Store [31,119] for the opening route's mining kit (owner 2026-10-26: Q34 -> the kit with
the remaining gold -> Q1): a Shovel (row m, 88 gold).  The in-store selector wanted to inscribe
the torches first, so ``_shop``'s buy fell back to the observe-and-leave path (ESC), and the
outside composition staged ``pm1\\r\\r\\x1b`` behind the entry key '5'.  On the re-opened page the
staged release was the shop-buy owner's second decision on the same shelf in the same durable
state -- the observe-and-leave had counted it once -- so the arbiter retired shop-buy at the
release (recurrence 2/2) and the log-only CLI turned the purchase into ESC.  Nothing changed, so
the visit composed the same one-shot again, four times, until ``town:blocked:stage-deadline:buy``.
The missing Recall/Teleport/CCW were not on any shelf; the Shovel was affordable throughout.

Fix (policy_town.py ``_town_arbiter_progress_vector``): a shop-buy shelf vector names the
operation its store visit has posted, so the release is a later step than the observation.  A
release that keeps failing returns to the bare observation, which still recurs.

Rows 0-32 of the capture's town-arrival journal replay through the public ``choose_key`` and the
live CLI's owner-retirement entrance (--owner-retired-log-only, as the viewing bots run).
DECLARED CONSTRUCTED after row 32: the boards after the posted purchase come from a minimal town
world (``TownWorld``) built from the recorded store pages and the recorded entrances: native
travel lands on its store's page, a step moves one cell, ESC leaves, a purchase pays the shelf
price with the game's receipt (store/purchase-order.cpp).  It ends when the visit turns to Q1's
preparation (``opening-q1:`` / ``fixedquest:``), which it does not model.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hengbot.cli import _handle_owner_retirement
from hengbot.model import parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-527-poor-buy-1116"
LOG_ONLY = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
OBSERVE_ROW = 30
RELEASE_ROW = 32
RELEASE = "pm1\r\r\x1b"
SHOVEL_PRICE = 88
# The recorded store entrances of the Outpost: store type -> (x, y).
ENTRANCES = {0: (119, 31), 1: (105, 32), 2: (91, 31), 3: (77, 31), 4: (91, 37),
             5: (106, 38), 6: (84, 45), 7: (123, 45), 8: (81, 38), 9: (97, 44)}
STEPS = {"1": (-1, 1), "2": (0, 1), "3": (1, 1), "4": (-1, 0), "5": (0, 0),
         "6": (1, 0), "7": (-1, -1), "8": (0, -1), "9": (1, -1)}
LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


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
    """DECLARED CONSTRUCTED: the boards after the posted purchase (module docstring)."""

    def __init__(self, board, pages):
        self.cur = board
        self.pages = pages
        self.turn = board["turn"]
        self.purchases = []

    def _tick(self, raw, messages=()):
        self.turn += 10
        raw["turn"] = self.turn
        raw["messages"] = list(messages)
        raw["type"] = "store" if raw.get("store") else "player_turn"
        return raw

    def _page(self, store_type):
        raw = copy.deepcopy(self.cur)
        x, y = ENTRANCES[store_type]
        raw["player"] = dict(raw["player"], x=x, y=y)
        raw["store"] = copy.deepcopy(self.pages[store_type])
        return self._tick(raw)

    def apply(self, key):
        cur = self.cur
        store = (cur.get("store") or {}).get("store_type")
        travel = re.fullmatch(r"\x1b?`n(.)\.", key)
        if travel:
            self.cur = self._page(ord(travel.group(1)) - ord("!"))
            return True
        if key in STEPS and store is None:
            dx, dy = STEPS[key]
            x, y = cur["player"]["x"] + dx, cur["player"]["y"] + dy
            entered = next((kind for kind, cell in ENTRANCES.items() if cell == (x, y)), None)
            cur["player"] = dict(cur["player"], x=x, y=y)
            self.cur = (self._page(entered) if entered is not None
                        else self._tick(copy.deepcopy(cur)))
            return True
        if store is not None and key == "\x1b":
            raw = copy.deepcopy(cur)
            raw["store"] = None
            self.cur = self._tick(raw)
            return True
        buy = re.fullmatch(r"p([A-Za-z])(\d*)\r*\x1b?", key)
        if buy and store is not None:
            letter, quantity = buy.group(1), int(buy.group(2) or 1)
            raw = copy.deepcopy(cur)
            ware = next(item for item in raw["store"]["items"] if item["letter"] == letter)
            raw["player"] = dict(raw["player"], gold=raw["player"]["gold"] - ware["price"] * quantity)
            bought = {k: v for k, v in ware.items() if k not in ("letter", "price")}
            bought["count"] = quantity
            pack = [dict(item) for item in raw["inventory"]] + [bought]
            pack.sort(key=lambda item: (-item["tval"], item.get("sval", 0)))
            for index, item in enumerate(pack):
                item["slot"] = LETTERS[index]
            raw["inventory"] = pack
            wares = [item for item in raw["store"]["items"] if item is not ware]
            if ware["count"] > quantity:
                wares.insert(raw["store"]["items"].index(ware),
                             dict(ware, count=ware["count"] - quantity))
            raw["store"]["items"] = wares
            self.pages[store] = raw["store"]
            messages = [f"{ware['name']}を ${ware['price']}で購入しました。",
                        f"{bought['name']}({bought['slot']})を手に入れた。"]
            if key.endswith("\x1b"):
                raw["store"] = None
            self.cur = self._tick(raw, messages)
            self.purchases.append((store, ware["name"], ware["price"] * quantity))
            return True
        return False


class ReleaseTest(unittest.TestCase):

    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.policy, self.recorded, self.steps = load(FIXTURE, Path(scratch.name))

    def replay(self, rows):
        """Decide ``rows`` as live; returns (board, choose_key, posted) of the last one."""
        for row, supply in rows:
            board = supply()
            before = copy.copy(self.policy._store_visit)
            key = self.policy.choose_key(board)
            self.assertEqual((key, self.policy.last_reason), (row["key"], row["reason"]),
                             f"row {row['row']}")
            posted = post(self.policy, board, key, before)
        return board, key, posted

    def test_the_capture_composed_the_same_one_shot_until_the_stage_deadline(self):
        rounds = [(row["key"], row["reason"]) for row in self.recorded[OBSERVE_ROW:]]
        cycle = [("", "shop:observe-and-leave"), ("5", "shop:one-shot-buy"),
                 (RELEASE, "shop:one-shot-buy"), ("5", "shop:travel:await-entry")]
        self.assertEqual(rounds, cycle * 4 + [cycle[0], ("5", "town:blocked:stage-deadline:buy")])
        page = json.loads(self.recorded[RELEASE_ROW]["line"])
        shovel = next(item for item in page["store"]["items"] if item["letter"] == "m")
        self.assertEqual((shovel["tval"], shovel["price"], page["player"]["gold"]),
                         (20, SHOVEL_PRICE, 161))

    def test_the_release_is_posted_and_the_visit_goes_on_to_q1(self):
        # One replay (it is slow): the observed shelf, the release, then the constructed world.
        board, _key, _posted = self.replay(self.steps[:OBSERVE_ROW + 1])
        observed = self.policy._town_arbiter_progress_vector(board, "shop:observe-and-leave")
        self.assertEqual(observed[-1], ("shelf", "shop-buy", (0, 0, 0), 0))
        visit = self.policy._store_visit
        # The staged release names its operation; without one the shelf is the observation.
        self.policy._store_visit = copy.copy(visit)
        self.policy._store_visit.operation_posted = True
        self.policy._store_visit.operation_key = RELEASE
        released = self.policy._town_arbiter_progress_vector(board, "shop:one-shot-buy")
        self.assertEqual(released[-1], observed[-1] + (("operation", RELEASE),))
        self.policy._store_visit = visit
        self.assertEqual(
            self.policy._town_arbiter_progress_vector(board, "shop:observe-and-leave"), observed)

        _board, key, posted = self.replay(self.steps[OBSERVE_ROW + 1:RELEASE_ROW + 1])
        self.assertEqual((key, posted), (RELEASE, RELEASE))
        self.assertFalse(self.policy._town_turn_arbiter.telemetry["retired"])

        pages = {}
        for entry in self.recorded[:RELEASE_ROW + 1]:
            raw = json.loads(entry["line"]) if entry["line"] else None
            if raw and raw.get("store"):
                pages[raw["store"]["store_type"]] = raw["store"]
        world = TownWorld(json.loads(self.recorded[RELEASE_ROW]["line"]), pages)
        self.assertTrue(world.apply(posted))
        reasons = []
        for _ in range(80):
            self.policy.observe_store_screen(world.cur.get("store") is not None)
            board = parse_snapshot(copy.deepcopy(world.cur), self.policy._monrace_knowledge)
            before = copy.copy(self.policy._store_visit)
            key = self.policy.choose_key(board)
            reasons.append(self.policy.last_reason)
            posted = post(self.policy, board, key, before)
            self.assertFalse(self.policy.last_reason.startswith("town:blocked"), reasons)
            if reasons[-1].startswith(("opening-q1:", "fixedquest:")):
                break
            self.assertTrue(world.apply(posted), (posted, reasons))
        # The kit is bought once and the visit leaves the buy stage for Q1's preparation.
        self.assertTrue(reasons[-1].startswith(("opening-q1:", "fixedquest:")), reasons)
        self.assertEqual(world.purchases[0], (0, "シャベル (1d2) (+0,+0) (+1) {+掘}", SHOVEL_PRICE))
        self.assertNotIn("shop:one-shot-buy", reasons)
        self.assertNotIn(0, [store for store, _name, _price in world.purchases[1:]])

if __name__ == "__main__":
    unittest.main()
