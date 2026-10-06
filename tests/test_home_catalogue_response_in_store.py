"""Pin the in-Home equipment catalogue response adoption from 2026-10-07."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

import tests  # noqa: F401 -- protect live runtime files
from hengbot.cli import _dispatch_response_lines
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import HOME_KNOWLEDGE_MACRO
from hengbot.claim_register import observe


FIXTURE = Path(__file__).parent / "fixtures"


class HomeCatalogueResponseInStoreTest(unittest.TestCase):
    def test_recorded_response_is_adopted_without_reposting_home_scan(self):
        pin = json.loads((FIXTURE / "home-catalogue-response-in-store-20261007.json")
                         .read_text(encoding="utf8"))
        page_fixture = json.loads((FIXTURE / "home-catalogue-burst-20261007.json")
                                  .read_text(encoding="utf8"))
        page = parse_snapshot(page_fixture, {})
        self.assertEqual(pin["pin"]["expected_in_home_requests"], 1)
        self.assertEqual(len(pin["response"]["knowledge"]["items"]),
                         pin["pin"]["response_item_count"])
        self.assertEqual((page.store.store_type, page.store.stock_num,
                          page.store.page_size, len(page.store.items)),
                         (7, 239, 52, 52))

        policy = HengbotPolicy()
        holder = policy._claim_register.declare(
            "equipment-txn",
            observe((str(page.turn), str(page.store.store_type), "knowledge"),
                    8, "knowledge"),
        )
        policy._claim_register.declare_execution(
            holder.claim_id, producer="equipment-txn",
            work_id="equipment:acquire-home-catalog", state="acting",
            next_step="home.catalogue.acquire",
            expected_effect="home-catalog-available",
            continuation="home.catalogue.acquire",
        )

        self.assertEqual(policy._home_catalogue_work_key(page), HOME_KNOWLEDGE_MACRO)
        policy.confirm_key_posted(HOME_KNOWLEDGE_MACRO)
        self.assertTrue(policy._home_knowledge_scan_inflight)

        with TemporaryDirectory() as directory:
            self.assertEqual(_dispatch_response_lines(
                [json.dumps(pin["response"])], policy, Mock(return_value=True),
                knowledge_ledger_path=Path(directory) / "knowledge.jsonl",
            ), 1)
        self.assertTrue(policy._home_knowledge_current)
        self.assertEqual(policy._home_scan_source, "~9")
        self.assertFalse(policy._home_knowledge_scan_inflight)

        key = policy._home_catalogue_work_key(page)
        self.assertEqual(key, "\x1b")
        self.assertEqual(policy.last_reason,
                         "equipment-transaction:home-catalog-acquired")
        self.assertTrue(policy._home_knowledge_current)
        self.assertFalse(policy._home_knowledge_scan_inflight)


if __name__ == "__main__":
    unittest.main()
