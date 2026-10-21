"""Recorded pins: one composer for store item keys, admitted for its owner.

Root type "store operation composition / quantity prompt" (#67 #74 #92, the
4th time).  Live soak c4-a 2026-10-21 on 43872194 / 95da0d01, three stops
``stuck-prompt`` (09:20:09, 12:07:01, 13:06:38): each Home-full overweight
surplus sale (#98 S7) inscribed its item (``{f@0\\r`` / ``{b@0\\r`` /
``{g@0\\r``, ``shop:in-store-inscribe``) and then decided ``d0y`` with reason
``town:overweight-surplus-sold:home-full``.  The runner refused the key at
admission (``phase=admission ... reason=map command on store screen``, the
posted-characters log has no character of ``d0y``).  Measured: the sold
items were single items (鑑定の巻物 {@0} x1, 重傷の治癒の薬 {@0} x1,
鑑定の巻物 {@0} x1), so ``d0y`` was the game's own prompt sequence
(store/sell-order.cpp store_sell: no quantity for one item, then
prompt_to_sell's [Y/n]); the refusal came from the executor's store-producer
admission, which knew only the ``shop:``/``home:``/``equipment-transaction:``
prefixes although ``_IN_STORE_OPERATION_OWNERS`` names this owner.

Fixture rows (the last state row of each capture, and the Black Market page
of the 12:28:29 capture): 0-2 the store page after each inscription
(09:20:09 alchemist, 12:07:01 alchemist, 13:06:38 magic shop), 3 the Black
Market page at turn 3846682 (Speed potions x6 on the shelf, 10 carried).

DECLARED CONSTRUCTED: the stack controls raise the count of the recorded
inscribed item (3) or of the recorded single shelf row; the executor pin
replays the recorded (key, owner) pair on the recorded alchemist board (its
shelf emptied) behind the harness's constructed English store screen (a
protocol control).
"""

from __future__ import annotations

import tests  # noqa: F401 -- isolate runtime state for standalone module runs
import copy
import gzip
import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.item_reservation import store_item_key
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests import test_classA_observed_input as classa
from tests import test_input_executor as executor_harness
from test_esp_threat_rest_recorded import EDIT, _policy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from item_sink_lint import analyze_repository, analyze_source  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "store-op-compose-root-20261021.jsonl.gz"
OWNER = "town:overweight-surplus-sold:home-full"


def _rows():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


class StoreItemComposerRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = _rows()
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _on(self, board):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        snapshot = parse_snapshot(board, self.monrace)
        policy.prime(snapshot)
        return policy, snapshot

    def test_recorded_inscribed_single_items_compose_the_recorded_sale(self):
        for row, slot in zip(self.rows[:3], "fbg"):
            with self.subTest(slot=slot):
                policy, snapshot = self._on(row)
                item = next(i for i in snapshot.inventory if i.slot == slot)
                self.assertEqual((item.inscription, item.count), ("@0", 1))
                self.assertEqual(store_item_key(policy, snapshot, "sell", item, "shop-sell",
                                                quantity=1, address="0"), "d0y")

    def test_stack_sale_answers_the_quantity_before_the_price_prompt(self):
        row = copy.deepcopy(self.rows[2])
        next(i for i in row["inventory"] if i["slot"] == "g")["count"] = 3
        policy, snapshot = self._on(row)
        item = next(i for i in snapshot.inventory if i.slot == "g")
        self.assertEqual(store_item_key(policy, snapshot, "sell", item, "shop-sell",
                                        quantity=2, address="0"), "d02\ry")

    def test_recorded_black_market_rows_compose_the_purchase_prompts(self):
        policy, snapshot = self._on(self.rows[3])
        speed = next(i for i in snapshot.store.items if i.letter == "m")
        self.assertEqual(speed.count, 6)
        self.assertEqual(store_item_key(policy, snapshot, "buy", speed, "shop-buy",
                                        quantity=6), "pm6\r\r")
        single = replace(speed, count=1)
        self.assertEqual(store_item_key(policy, snapshot, "buy", single, "shop-buy",
                                        quantity=1), "pm\r")

    def test_home_deposit_and_withdrawal_ask_only_the_quantity(self):
        policy, snapshot = self._on(self.rows[2])
        cure = next(i for i in snapshot.inventory if i.slot == "b")
        self.assertEqual(cure.count, 10)
        self.assertEqual(store_item_key(policy, snapshot, "deposit", cure, "home-visit",
                                        quantity=4), "db4\r")
        single = next(i for i in snapshot.inventory if i.slot == "g")
        self.assertEqual(store_item_key(policy, snapshot, "deposit", single, "home-visit",
                                        quantity=1), "dg")
        self.assertEqual(store_item_key(policy, snapshot, "withdraw", cure, "home-visit",
                                        quantity=3, address="c"), "pc3\r")

    def test_every_store_item_site_uses_the_composer(self):
        self.assertEqual(analyze_repository(), [])

    def test_store_item_key_outside_the_composer_fails(self):
        for expression in (
                'reserved_item_command(self, snapshot, "sell", item, "shop-sell", address=tag)',
                'reserved_item_command(self, snapshot, "buy", item, "shop-buy") + "\\r"',
                'reserved_item_command(self, snapshot, "deposit", item, "home-visit")',
                'reserved_item_command(self, snapshot, "withdraw", item, "x", address="a")',
                'checked_item_command(self, "sell", item, verdict)',
        ):
            with self.subTest(expression=expression):
                source = ("def new_sale(self, snapshot, item, tag, verdict):\n"
                          f" return {expression}\n")
                self.assertTrue(any("outside store_item_key" in finding
                                    for finding in analyze_source(source, names=set())))
        consumption = "def drink(self, snapshot, item):\n return reserved_item_command(self, snapshot, \"quaff\", item)\n"
        self.assertEqual(analyze_source(consumption, names=set()), [])


class SurplusSaleAdmissionRecordedTest(executor_harness.ProductionHarness):
    def _drive(self, owner):
        raw = _rows()[0]
        # DECLARED CONSTRUCTED: the constructed screen lists no ware, so the
        # recorded shelf is emptied to keep the store record coherent.
        raw["store"]["items"] = []
        initial = executor_harness.store_screen()
        return classa.ClassAObservedInputPins.drive(
            self, "d0y", owner, [executor_harness.store_screen()],
            initial=initial, raw=raw)

    def test_recorded_surplus_sale_owner_is_admitted_at_the_store(self):
        game, result = self._drive(OWNER)
        self.assertNotIn("map command on store screen", str(result.reason or ""))
        self.assertEqual((result.outcome, game.accepted), ("completed", ["d0y"]))

    def test_map_owner_is_still_refused_at_the_store(self):
        game, result = self._drive("survival:map-command")
        self.assertEqual(game.accepted, [])
        self.assertEqual(result.reason.split("reason=")[-1], "map command on store screen")


if __name__ == "__main__":
    unittest.main()
