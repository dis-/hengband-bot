"""Recorded pin: optional sales must not spend the entry budget of a required buy.

Live soak 2026-10-19 05:41 (issue #74), Level 29, store 5 (Magic shop),
gold 9,205: the Magic shop entry inscribed and sold four surplus devices
(``{k@0\\r``/``d0y``, ``{k@0\\r``/``d0y``, ``{l@0\\r``/``d0y``,
``{l@0\\r``/``d0y``).  The third sale released a 3-charge Identify staff;
from the next page on the in-store selection wanted the departure-blocking
Identify staff purchase (row ``m``, 鑑定の杖 (5x 15回分)), but the shop
selector kept starting the next surplus sale.  The eight operations spent
the entry budget (``STORE_STUCK_LIMIT``) and the visit ended in
``town:blocked:shop-required-operation-uncomposable`` (cause
``entry-budget``) with the required buy still on the page.

Fixture rows (raw lines of the captured state log): the Home ``~9`` list,
the outside board at the Magic shop door, and the nine store pages the bot
decided on (decisions 7052..7060).

DECLARED CONSTRUCTED: a fresh policy primed on the captured door board with
in-store operations on (the soak runs ``-InStoreShopOps``) and the Home
knowledge applied; each captured page is the game's answer to the key the
bot posted on the previous page.  After the fixed decision differs from the
captured key the remaining captured pages no longer apply.
"""

from __future__ import annotations

import tests  # noqa: F401 -- isolate runtime state for standalone module runs
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _parse_items
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "store-entry-budget-20261019.jsonl.gz"
STOP = "town:blocked:shop-required-operation-uncomposable"
CAPTURED = [
    ("{k@0\r", "shop:in-store-inscribe"),
    ("d0y", "shop:in-store-sell"),
    ("{k@0\r", "shop:in-store-inscribe"),
    ("d0y", "shop:in-store-sell"),
    ("{l@0\r", "shop:in-store-inscribe"),
    ("d0y", "shop:in-store-sell"),
    ("{l@0\r", "shop:in-store-inscribe"),
    ("d0y", "shop:in-store-sell"),
    ("\x1b", STOP),
]


class StoreEntryBudgetRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        cls.home, cls.door = rows[:2]
        cls.pages = rows[2:]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _policy(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        policy._in_store_ops_enabled = True
        snapshot = parse_snapshot(self.door, self.monrace)
        policy.prime(snapshot)
        policy._skill_exp_cache = (
            0, 0, snapshot.player.level, policy._town_visit_epoch
        )
        policy.consume_home_knowledge(tuple(_parse_items(
            self.home["knowledge"]["items"],
            protocol=self.home.get("protocol_version"),
        )))
        return policy

    def _decide(self, policy, board):
        snapshot = parse_snapshot(board, self.monrace)
        policy.observe_store_screen(True)
        key = policy.choose_key(snapshot)
        policy.confirm_key_posted(key)
        return str(key), policy.last_reason

    def _replay(self):
        policy = self._policy()
        keys = []
        for page in self.pages:
            keys.append(self._decide(policy, page))
            if keys[-1] != CAPTURED[len(keys) - 1]:
                break
        return policy, keys

    def test_captured_boards(self):
        self.assertEqual(
            [(row["turn"], (row.get("store") or {}).get("store_type"),
              row["player"]["gold"]) for row in [self.door, *self.pages]],
            [(3266048, None, 9205)] + [(3266048, 5, gold) for gold in (
                9205, 9205, 9555, 9555, 9735, 9735, 9940, 9940, 10167)],
        )

    def test_required_identify_staff_is_bought_before_the_next_surplus_sale(self):
        policy, keys = self._replay()
        # af25b541 replays the captured inscription of the fourth surplus
        # device here; its sale then spends the eighth operation and the
        # next page ends in the entry-budget stop.
        self.assertEqual(keys[:6], CAPTURED[:6])
        self.assertEqual(len(keys), 7, keys)
        key, reason = keys[6]
        self.assertEqual((key[:2], reason), ("pm", "shop:in-store-buy"), keys)
        self.assertNotIn(STOP, [reason for _, reason in keys])
        self.assertIsNone(policy._town_blocked_reason)

    def test_control_surplus_sales_before_the_requirement_are_unchanged(self):
        # Control: an ordinary sale-only continuation (pages 2..6, the entry
        # has already operated, no departure-blocking purchase yet) keeps
        # selling its surplus devices in the captured order.
        policy, keys = self._replay()
        self.assertEqual(keys[:6], CAPTURED[:6])


if __name__ == "__main__":
    unittest.main()
