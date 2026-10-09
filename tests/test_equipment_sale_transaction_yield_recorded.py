"""The 2026-10-08 Home-route stop must yield to its prepared sale plan."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import tests  # noqa: F401
from hengbot.equipment_transaction_planner import (
    EquipmentTransaction,
    EquipmentTransactionPlan,
    PHASE_HOME_FINALIZE,
)
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.model import _parse_items, parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy
from hengbot.warrior_optimization import load_character_calibration
from test_equipment_optimizer_sales import measurement


FIXTURE = Path(__file__).parent / "fixtures/equipment-sale-transaction-yield-20261008.json.gz"
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
    "501095788ada36de15ca46ef5015f03f4a335bbc4e7a36ae58c90d195fa780d5"
)


def _lore(data):
    result = {}
    for key, value in data["knowledge"].items():
        value["flags"] = frozenset(value["flags"])
        value["abilities"] = frozenset(value["abilities"])
        value["blows"] = tuple(
            row if isinstance(row, MonsterBlow) else MonsterBlow(**row)
            for row in value["blows"]
        )
        result[int(key)] = MonraceKnowledge(**value)
    return result


class EquipmentSaleTransactionYieldRecordedTest(unittest.TestCase):
    def test_built_sale_runs_before_home_route_terminal_without_losing_stripped_items(self):
        pin = json.loads(gzip.decompress(FIXTURE.read_bytes()))
        self.assertEqual(
            pin["terminal_stop"]["reason"],
            "equipment-transaction:home-route-repeat-terminal",
        )
        self.assertEqual(pin["sale_built_stop"]["equipment_sale"]["items"], 106)
        self.assertEqual(pin["sale_built_stop"]["equipment_sale"]["withdrawals"], 3)

        data, catalog, _recorded_snapshot, _evaluator, _options = (
            measurement.recorded_inputs()
        )
        lore = _lore(data)
        board = parse_snapshot(pin["board"], lore)
        policy = HengbotPolicy(monrace_knowledge=lore)
        policy.consume_skill_knowledge(data["skill"])
        board = policy._with_cached_skill_exp(board)
        policy.prime(board)
        home = tuple(_parse_items(
            data["home"]["knowledge"]["items"],
            protocol=data["home"]["protocol_version"],
        ))
        policy.consume_home_knowledge(home)
        policy._equipment_catalog = catalog  # TEST_FAKERY_LINT_ALLOW: private-state-injected: replay reconstructs the captured optimizer catalogue
        policy._equipment_catalog.refresh_carried(board.inventory, board.equipment)
        policy._home_knowledge_items = home
        policy._home_knowledge_current = True
        policy._home_knowledge_invalidated = False
        policy._home_scan_item_count = len(home)
        policy._home_capacity_observation = (
            240, 240, policy._effective_town_id(board),
        )

        with tempfile.TemporaryDirectory(prefix="sale-transaction-yield-") as directory:
            calibration_path = Path(directory) / "character-calibration.json"
            calibration_path.write_text(
                json.dumps(data["calibration"]), encoding="utf-8",
            )
            policy._character_calibration = load_character_calibration(
                calibration_path
            )
            policy._character_calibration_loaded = True
            policy._ensure_equipment_sale_session(board)
            policy._equipment_sale_session["sale_needed"] = True
            policy._build_equipment_sale_session(board)

        self.assertTrue(policy._equipment_sale_session["built"])
        self.assertEqual(len(policy._equipment_sale_session["items"]), 106)

        # DECLARED CONSTRUCTED transaction checkpoint: the captured stop did
        # not retain a policy checkpoint, so reconstruct the blocked Home
        # deposit and its stripped-item ownership from the recorded failure.
        transaction = EquipmentTransactionSession(EquipmentTransactionPlan((
            EquipmentTransaction(
                PHASE_HOME_FINALIZE, "deposit", "live-item", "body", "live-identity",
            ),
        ), (), 0))
        transaction.block("home-route-unavailable")
        held_items = [("live-identity", "body")]
        policy._equipment_transaction_session = transaction
        policy._equipment_transaction_owned_items = list(held_items)

        key = policy.choose_key(board)

        self.assertEqual(policy.last_reason, "shop:travel")
        self.assertTrue(key.startswith("\x1b`n"))
        self.assertIs(policy._equipment_transaction_session, transaction)
        self.assertEqual(policy._equipment_transaction_owned_items, held_items)
        self.assertEqual(transaction.blockers, ["home-route-unavailable"])
        self.assertIsNone(policy._equipment_transaction_route_terminal)
        sale = policy._equipment_sale_session
        self.assertEqual(sale["withdrawals"], 3)  # Three planned batch slots.
        self.assertEqual(len(sale["batch"]), 3)
        self.assertEqual(sale["attempted"], set(sale["batch"]))

        # DECLARED CONSTRUCTED batch completion: three withdrawals/sales have
        # freed Home slots. The same blocked deposit is executable again.
        policy._pending_disposal_item = None
        policy._home_pending_batch.clear()
        policy._home_capacity_observation = (
            239, 240, policy._effective_town_id(board),
        )
        self.assertFalse(policy._equipment_sale_should_yield_transaction(board))
        self.assertIs(policy._equipment_transaction_session, transaction)
        self.assertTrue(transaction.executable)
        self.assertEqual(transaction.current_action.kind, "deposit")
        self.assertEqual(transaction.blockers, [])


if __name__ == "__main__":
    unittest.main()
