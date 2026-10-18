"""Recorded pin: a sale inscription must not collide with a refused item's tag.

Live soak 2026-10-18 12:34 and 12:38 (issue #67), Level 26, store 4
(Alchemist): the pack carried an Identify staff inscribed ``{@0}`` (a staff
the Alchemist does not buy).  The Home-full sale withdrew a scroll stack and
the bot inscribed it ``@0`` too (``{h@0\\r`` / ``{j@0\\r``).  The next board
showed two ``@0`` items, the sale ended as
``shop:sale-inscription-ambiguous-leave`` and the in-store continuation,
which still wanted one Word of Recall (9/10, 8/10), stopped with
``town:blocked:shop-required-operation-uncomposable``.

Fixture rows (raw lines of the captured state logs): capture A (12:34) the
Home ``~9`` list, the outside board at the Alchemist door, the store page
before and after the inscription; capture B (12:38) the Home ``~9`` list,
the Home approach/visit/withdraw boards, the walk board, the store page
before and after the inscription.

DECLARED CONSTRUCTED: a fresh policy primed on the captured boards with
in-store operations on (the soak runs ``-InStoreShopOps``); the planned depth
is set to 20, which reproduces the captured Recall target 10 (9 + the
departure scroll); the skill-exp cache is filled; the post-inscription board
carries the tag the fixed policy posted, and the post-sale board is the
captured page with the sold row removed from the pack and the sale price
added to the gold.
"""

from __future__ import annotations

import tests  # noqa: F401 -- isolate runtime state for standalone module runs
import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _parse_items
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "sale-inscribe-buy-20261018.jsonl.gz"
RECALL = ("帰還の詔の巻物", 70, 11)
STOP = "town:blocked:shop-required-operation-uncomposable"


def _retag(board, slot, old, new):
    """Return ``board`` with ``slot``'s inscription ``old`` replaced by ``new``."""
    board = copy.deepcopy(board)
    item = next(item for item in board["inventory"] if item["slot"] == slot)
    item["inscription"] = item["inscription"].replace(old, new)
    item["name"] = item["name"].replace("{" + old + "}", "{" + new + "}")
    return board


def _sold(board, slot, price):
    """Return ``board`` after the game sold the whole ``slot`` stack."""
    board = copy.deepcopy(board)
    letters = [item["slot"] for item in board["inventory"]]
    board["inventory"] = [item for item in board["inventory"] if item["slot"] != slot]
    for item, letter in zip(board["inventory"], letters):
        item["slot"] = letter
    board["player"]["gold"] += price
    board["messages"] = []
    return board


def _bought(board, key):
    """Return ``board`` after the game sold ``key``'s row quantity to the pack."""
    board = copy.deepcopy(board)
    quantity = int(key[2:].rstrip("\r") or 1)
    row = next(item for item in board["store"]["items"] if item["letter"] == key[1])
    row["count"] -= quantity
    if row["count"] <= 0:
        board["store"]["items"].remove(row)
    board["player"]["gold"] -= row["price"] * quantity
    pack = copy.deepcopy(row)
    pack.pop("letter", None)
    pack.pop("price", None)
    pack["count"] = quantity
    pack["slot"] = "abcdefghijklmnopqrstuvw"[len(board["inventory"])]
    board["inventory"].append(pack)
    board["messages"] = []
    return board


class SaleInscribeBuyRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        cls.a_home, cls.a_door, cls.a_page, cls.a_tagged = rows[:4]
        (cls.b_home, cls.b_approach, cls.b_inside, cls.b_withdraw, cls.b_walk,
         cls.b_page, cls.b_tagged) = rows[4:]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _policy_for(self, home, board):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        policy._in_store_ops_enabled = True
        policy._equipment_optimization_last_depth = 20
        snapshot = parse_snapshot(board, self.monrace)
        policy.prime(snapshot)
        policy._skill_exp_cache = (
            0, 0, snapshot.player.level, policy._town_visit_epoch
        )
        policy.consume_home_knowledge(tuple(_parse_items(
            home["knowledge"]["items"], protocol=home.get("protocol_version"),
        )))
        return policy

    def _decide(self, policy, board):
        snapshot = parse_snapshot(board, self.monrace)
        if board.get("store"):
            policy.observe_store_screen(True)
        key = policy.choose_key(snapshot)
        policy.confirm_key_posted(key)
        return str(key), policy.last_reason

    def _captures(self, *, without_home_junk=False):
        """Yield (name, policy, page, tagged board, sold slot) at the inscription."""
        policy = self._policy_for(self.a_home, self.a_door)
        yield "12:34", policy, self.a_page, self.a_tagged, "h"
        b_home = self.b_home
        if without_home_junk:
            # DECLARED CONSTRUCTED wall (#70): the 12:38 Home's worthless
            # remains and emptied chest are marked as bounties (rows and
            # addresses kept), so the recorded scroll sale is still the
            # Home-full relief's choice.
            b_home = copy.deepcopy(b_home)
            for item in b_home["knowledge"]["items"]:
                if item["tval"] in {1, 3, 10} or (
                        item["tval"] == 7 and "(空)" in item["name"]):
                    item["is_bounty"] = True
        policy = self._policy_for(b_home, self.b_approach)
        self.b_decisions = [self._decide(policy, board)
                            for board in (self.b_inside, self.b_withdraw, self.b_walk)]
        yield "12:38", policy, self.b_page, self.b_tagged, "j"

    def test_captured_boards(self):
        self.assertEqual(
            [(row["turn"], (row.get("store") or {}).get("store_type"))
             for row in (self.a_door, self.a_page, self.a_tagged, self.b_approach,
                         self.b_inside, self.b_withdraw, self.b_walk, self.b_page,
                         self.b_tagged)],
            [(1663161, None), (1663161, 4), (1663161, 4), (1680812, None),
             (1680812, 7), (1680820, 7), (1680829, None), (1681065, 4),
             (1681065, 4)],
        )
        # The refused staff already carried @0 before the visit.
        for page in (self.a_page, self.b_page):
            self.assertEqual(
                [(item["name"], item["inscription"]) for item in page["inventory"]
                 if "@" in item["inscription"]],
                [(next(item["name"] for item in page["inventory"]
                       if item["tval"] == 55 and item["inscription"] == "@0"), "@0")],
            )

    def test_sale_inscription_avoids_refused_tag_then_sells_and_buys_recall(self):
        expected = {
            "12:34": ("pg1\r\r", "shop:in-store-buy"),
            "12:38": ("\x1b", "home:scan-leave-store"),
        }
        for name, policy, page, tagged, slot in self._captures():
            with self.subTest(capture=name):
                if name == "12:38":
                    # #70 owner decision 2026-10-18 ("不要品を先に壊す"): the
                    # full Home's worthless remains are destroyed before any
                    # surplus sale, so this visit withdraws a corpse to
                    # destroy instead of the recorded scroll sale.
                    self.assertEqual(self.b_decisions[0], (
                        "\x1b", "home:full-queue-surplus-withdraw"))
                    self.assertEqual(policy._home_full_relief["mode"], "destroy")
                    self.assertEqual(policy._home_full_relief["sale"][0][1], 10)
                    continue
                # 5ffac123 posted "{<slot>@0\r" here; the tagged board then
                # held two @0 items and ended in the uncomposable stop.
                key, reason = self._decide(policy, page)
                self.assertEqual((key, reason), (
                    "{" + slot + "@1\r", "shop:in-store-inscribe",
                ))

                # The game applied the posted tag.
                tagged = _retag(tagged, slot, "@0", "@1")
                key, reason = self._decide(policy, tagged)
                self.assertTrue(key.startswith("d1"), (key, reason))
                self.assertNotEqual(reason, STOP)
                entry = policy._batch_sell_pending["entries"][0]
                self.assertEqual(entry["tag"], "1")

                # The sale is observed.  The visit then buys (each posted
                # buy is reflected on the next page) until the required
                # Recall is posted, or leaves without the stop.
                board = _sold(tagged, slot, 1)
                keys = []
                for _ in range(4):
                    key, reason = self._decide(policy, board)
                    keys.append((key, reason))
                    self.assertNotEqual(reason, STOP, keys)
                    if not key.startswith("p"):
                        break
                    row = next(item for item in board["store"]["items"]
                               if item["letter"] == key[1])
                    if (row["name"], row["tval"], row["sval"]) == RECALL:
                        break
                    board = _bought(board, key)
                self.assertEqual(keys[-1], expected[name], keys)

    def test_control_ambiguous_tag_not_made_by_this_visit_does_not_sell(self):
        # Control: the captured post-inscription board with the pre-fix
        # pending tag 0 -- two different pack items carry @0, one of them
        # inscribed before this visit.  The game's tester could pick either;
        # the bot must leave without composing the sale.
        for name, policy, page, tagged, slot in self._captures(without_home_junk=True):
            with self.subTest(capture=name):
                self._decide(policy, page)
                pending =policy._batch_sell_pending
                pending["entries"][0]["tag"] = "0"
                key, reason = self._decide(policy, tagged)
                self.assertEqual(key, "\x1b")
                self.assertIsNone(policy._batch_sell_pending)
                self.assertIn(pending["entries"][0]["signature"],
                              policy._unsellable_items)


if __name__ == "__main__":
    unittest.main()
