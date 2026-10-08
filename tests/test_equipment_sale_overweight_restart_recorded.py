"""The 2026-10-08 restart must start equipment sales before deposits."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import tests  # noqa: F401
from hengbot.model import STORE_HOME, _parse_items, parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy
from hengbot.warrior_optimization import load_character_calibration
from tests.test_equipment_optimizer_sales import measurement


FIXTURE = Path(__file__).parent / "fixtures/equipment-sale-overweight-restart-20261008.json.gz"
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
    "54c2bb6ace8eeb980818f8a582d18b6677cd8ae8f6f6ff90acc16337ace9626f"
)


class EquipmentSaleOverweightRestartRecordedTest(unittest.TestCase):
    def test_restarted_overweight_town_starts_sale_ahead_of_deposit_stop(self):
        pin = json.loads(gzip.decompress(FIXTURE.read_bytes()))
        self.assertEqual(
            pin["recorded_stop"]["reason"],
            "town:blocked:overweight-home-unreachable",
        )
        self.assertEqual(pin["observed_full_home"]["store"]["stock_num"], 240)
        self.assertEqual(pin["observed_full_home"]["store"]["capacity"], 240)

        data, catalog, _recorded_snapshot, _evaluator, _options = (
            measurement.recorded_inputs()
        )
        monrace_knowledge = {}
        for key, value in data["knowledge"].items():
            value["flags"] = frozenset(value["flags"])
            value["abilities"] = frozenset(value["abilities"])
            value["blows"] = tuple(
                row if isinstance(row, MonsterBlow) else MonsterBlow(**row)
                for row in value["blows"]
            )
            monrace_knowledge[int(key)] = MonraceKnowledge(**value)

        board = parse_snapshot(pin["restart_board"], monrace_knowledge)
        policy = HengbotPolicy(monrace_knowledge=monrace_knowledge)
        policy.consume_skill_knowledge(data["skill"])
        board = policy._with_cached_skill_exp(board)
        policy.prime(board)
        home = tuple(_parse_items(
            data["home"]["knowledge"]["items"],
            protocol=data["home"]["protocol_version"],
        ))
        policy.consume_home_knowledge(home)
        policy._equipment_catalog = catalog
        policy._equipment_catalog.refresh_carried(board.inventory, board.equipment)
        policy._home_knowledge_items = home
        policy._home_knowledge_current = True
        policy._home_knowledge_invalidated = False
        policy._home_scan_item_count = len(home)
        policy._home_capacity_observation = (
            pin["observed_full_home"]["store"]["stock_num"],
            pin["observed_full_home"]["store"]["capacity"],
            policy._effective_town_id(board),
        )
        policy._equipment_sale_session = None
        with tempfile.TemporaryDirectory(prefix="sale-overweight-calibration-") as directory:
            calibration_path = Path(directory) / "character-calibration.json"
            calibration_path.write_text(
                json.dumps(data["calibration"]), encoding="utf-8"
            )
            policy._character_calibration = load_character_calibration(
                calibration_path
            )
            policy._character_calibration_loaded = True

            needs = policy._town_need_candidates(board)

        sale_need = next(need for need in needs
                         if need.category == "equipment-sale")
        weight_need = next(need for need in needs
                           if need.category == "weight-overload")
        self.assertLessEqual(
            policy._town_need_effective_phase(board, sale_need),
            policy._town_need_effective_phase(board, weight_need),
        )
        self.assertTrue(policy._equipment_sale_session["built"])
        self.assertTrue(policy._equipment_sale_session["items"])
        by_signature = {
            item["signature"]: item
            for item in policy._equipment_sale_session["items"]
        }
        pack_sales = [item for item in by_signature.values()
                      if item["origin"] == "pack"]
        if pack_sales:
            selected = by_signature[policy._pending_disposal_item]
            self.assertEqual(selected["origin"], "pack")
        else:
            selected = by_signature[policy._equipment_sale_session["batch"][0]]
            self.assertEqual(selected["origin"], "home")
            self.assertEqual(sale_need.store_type, STORE_HOME)


if __name__ == "__main__":
    unittest.main()
