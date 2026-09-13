from __future__ import annotations

import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.home_disposal import HomeDisposalState
from hengbot.model import (
    STORE_ALCHEMIST, STORE_TEMPLE, SV_SCROLL_DETECT_TREASURE,
    StoreItem, parse_snapshot,
)
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).parent / "fixtures" / "recall-stockout-surplus-incident.jsonl.gz"


def replay_to_home_return(policy: HengbotPolicy):
    knowledge = {}
    decisions = []
    final_snapshot = None
    with gzip.open(FIXTURE, "rt", encoding="utf-8-sig") as stream:
        for index, line in enumerate(stream, 1):
            raw = json.loads(line)
            if raw.get("type") == "knowledge":
                knowledge.update(raw.get("knowledge", {}))
                continue
            snapshot = parse_snapshot(raw, knowledge)
            key = policy.choose_key(snapshot)
            decisions.append((index, snapshot.turn, key, policy.last_reason))
            final_snapshot = snapshot
            if index == 24:
                break
    return decisions, final_snapshot


def fixture_snapshot(record: int):
    knowledge = {}
    with gzip.open(FIXTURE, "rt", encoding="utf-8-sig") as stream:
        for index, line in enumerate(stream, 1):
            raw = json.loads(line)
            if raw.get("type") == "knowledge":
                knowledge.update(raw.get("knowledge", {}))
            elif index == record:
                return parse_snapshot(raw, knowledge)
    raise AssertionError(f"fixture record {record} not found")


class RecallStockoutSurplusPins(unittest.TestCase):
    def _state(self, root: Path, transactions=()):
        history = root / "home-withdraw-history.jsonc"
        history.write_text(
            json.dumps({"version": 1, "dungeon_recall_count": 0,
                        "transactions": list(transactions)}),
            encoding="utf-8",
        )
        return HomeDisposalState(
            history,
            root / "home-disposal-decisions.jsonc",
            root / "queue.json",
            root / "events.jsonl",
        )

    def test_home_surplus_incident_real_producer(self):
        """Public rows 1-24 produce and consume the bound deposit on one policy."""
        with TemporaryDirectory() as directory:
            decisions, snapshot = replay_to_home_return(
                HengbotPolicy(home_disposal_state=self._state(Path(directory)))
            )
        self.assertEqual(decisions[-1][2:], ("5", "home:atomic-deposit"))
        self.assertEqual(snapshot.turn, 2856373)

    def test_future_history_does_not_suppress_surplus(self):
        """A future deposit record is history, not a surplus-selection veto."""
        with TemporaryDirectory() as empty_dir, TemporaryDirectory() as future_dir:
            ordinary, _ = replay_to_home_return(
                HengbotPolicy(home_disposal_state=self._state(Path(empty_dir)))
            )
            future = ({"action": "deposit", "signature": ["油つぼ", 77, 0],
                       "turn": 2856373},)
            with_history, _ = replay_to_home_return(
                HengbotPolicy(
                    home_disposal_state=self._state(Path(future_dir), future)
                )
            )
        self.assertEqual(ordinary[-1][2:], ("5", "home:atomic-deposit"))
        self.assertEqual(with_history[-1][2:], ordinary[-1][2:])

    def test_identify_first_and_no_open_home_unbound_deposit(self):
        """The captured pre-Home producer acts before the later bound deposit."""
        with TemporaryDirectory() as directory:
            decisions, _ = replay_to_home_return(
                HengbotPolicy(home_disposal_state=self._state(Path(directory)))
            )
        first_disposal = next(i for i, row in enumerate(decisions)
                              if row[3] == "inventory:destroy-disposable-item")
        deposit = next(i for i, row in enumerate(decisions)
                       if row[3] == "home:atomic-deposit")
        self.assertLess(first_disposal, deposit)
        self.assertNotIn(
            "home:route-claim-unfulfilled", [row[3] for row in decisions]
        )

    def test_stockout_owned_home_kit_plans_exactly_one_prepared_run(self):
        """Regression for H1: Home-owned kit is usable without being carried."""
        with TemporaryDirectory() as directory:
            policy = HengbotPolicy(
                home_disposal_state=self._state(Path(directory))
            )
            _decisions, _ = replay_to_home_return(policy)
            snapshot = fixture_snapshot(39)
            digger = next(item for item in snapshot.inventory if item.is_digging_tool)
            detection = replace(
                snapshot.inventory[0], name="財宝感知の巻物", tval=70,
                sval=SV_SCROLL_DETECT_TREASURE,
                count=1, slot="z",
            )
            policy._equipment_catalog.complete_home_scan([digger])
            policy._home_knowledge_items = (detection,)
            policy._town_supplier_stock.clear()
            policy._town_visit_ledger.shelf_observations.clear()
            for store_type in (STORE_TEMPLE, STORE_ALCHEMIST):
                policy._town_visit_ledger.shelf_observations[
                    (store_type, "recall")
                ] = ()
            policy._town_restock_rechecked.update((STORE_TEMPLE, STORE_ALCHEMIST))
            policy._town_restock_wait_until = None

            key = policy._recall_restock_key(snapshot)

        self.assertEqual((key, policy.last_reason), ("5", "town:recall-stockout-mining"))
        self.assertEqual((policy._fundraising_mode, policy._planned_mining_runs), ("prepare", 1))

    def test_unaffordable_recall_page_starts_fundraising_not_restock(self):
        """Regression for H2: visible recall at a high price is a gold gap."""
        with TemporaryDirectory() as directory:
            policy = HengbotPolicy(
                home_disposal_state=self._state(Path(directory))
            )
            _decisions, snapshot = replay_to_home_return(policy)
            recall = next(item for item in snapshot.inventory if item.is_recall_scroll)
            page = replace(snapshot, store=None)
            # StoreState is absent on the outside capture; reuse its public
            # constructor through the model type of a captured Home page.
            if page.store is None:
                with gzip.open(FIXTURE, "rt", encoding="utf-8-sig") as stream:
                    knowledge = {}
                    for index, line in enumerate(stream, 1):
                        raw = json.loads(line)
                        if raw.get("type") == "knowledge":
                            knowledge.update(raw.get("knowledge", {}))
                        elif index == 21:
                            home_page = parse_snapshot(raw, knowledge).store
                            break
                page = replace(
                    snapshot,
                    store=replace(
                        home_page, store_type=STORE_TEMPLE,
                        items=(StoreItem(
                            "a", recall.name, 2, recall.tval, recall.sval,
                            snapshot.player.gold + 1,
                        ),),
                    ),
                )
            policy._town_restock_waiting_for = (STORE_TEMPLE, STORE_ALCHEMIST)
            policy._observe_restock_supplier_page(page)

        self.assertEqual((policy._fundraising_mode, policy._planned_mining_runs), ("prepare", 1))
        self.assertNotIn(STORE_TEMPLE, policy._town_restock_rechecked)


if __name__ == "__main__":
    unittest.main()
