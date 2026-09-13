from __future__ import annotations

import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from policy_fixtures import item
from hengbot.home_disposal import HomeDisposalState
from hengbot.model import (
    STORE_ALCHEMIST, STORE_TEMPLE, SV_LITE_TORCH,
    SV_SCROLL_DETECT_TREASURE, SV_SCROLL_IDENTIFY, TVAL_LITE, TVAL_SCROLL,
    StoreItem, parse_snapshot,
)
from hengbot.policy import HengbotPolicy
from hengbot.cli import _consume_response_sequence


FIXTURE = Path(__file__).parent / "fixtures" / "recall-stockout-surplus-incident.jsonl.gz"
AUTO_ENTRY_FIXTURE = (
    Path(__file__).parent / "fixtures" /
    "barrier-home-auto-entry-lines-1-23.jsonl.gz"
)


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

    def test_barrier_bound_open_home_page_posts_one_surplus_batch(self):
        """Stage-2e lines 1-23 drive the real policy through Home auto-entry."""
        with TemporaryDirectory() as directory:
            policy = HengbotPolicy(
                home_disposal_state=self._state(Path(directory)))
            # pin_vacuity: calibration is an unrelated collaborator in this
            # archived warrior save; the real route/Home/deposit producers run.
            policy._calibration_active = lambda: False
            knowledge = {}
            decisions = []
            with gzip.open(AUTO_ENTRY_FIXTURE, "rt", encoding="utf-8-sig") as stream:
                for index, line in enumerate(stream, 1):
                    raw = json.loads(line)
                    _consume_response_sequence(
                        [line], policy, lambda *_args, **_kwargs: True,
                        knowledge, parse_snapshots=False,
                        knowledge_ledger_path=Path(directory) / "knowledge.jsonl",
                    )
                    if raw.get("type") == "knowledge":
                        knowledge.update(raw.get("knowledge", {}))
                        continue
                    snapshot = parse_snapshot(raw, knowledge)
                    if index in (21, 22):
                        # The production executor owns Home auto-entry here;
                        # this outside JSONL observation is drained, not decided.
                        continue
                    key = policy.choose_key(snapshot)
                    decisions.append((index, key, policy.last_reason))
                    if key.startswith("~9"):
                        policy.confirm_key_posted(key)

        self.assertEqual(decisions[-1][0], 23)
        self.assertEqual(decisions[-1][2], "home:atomic-deposit")
        self.assertTrue(decisions[-1][1].startswith("d"))
        self.assertTrue(decisions[-1][1].endswith("da6\r\x1b"))
        self.assertEqual(decisions[-1][1].count("da6\r"), 1)
        self.assertEqual(
            policy._home_atomic_deposit_pending[0][-1][1:], (6, 6))
        self.assertNotIn("home:route-claim-unfulfilled",
                         [reason for _index, _key, reason in decisions])

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
            snapshot = fixture_snapshot(24)
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

    def test_reliable_identify_source_protects_unknown_surplus(self):
        """M1 regression: a promising unknown cannot be deposited first."""
        with TemporaryDirectory() as directory:
            policy = HengbotPolicy(
                home_disposal_state=self._state(Path(directory))
            )
            snapshot = fixture_snapshot(24)
            unknown = item(
                "z", TVAL_LITE, SV_LITE_TORCH, known=False,
                fully_known=False, pseudo_feeling="excellent", fuel=0,
                is_equipment=True,
            )
            identify = item("y", TVAL_SCROLL, SV_SCROLL_IDENTIFY, count=1)
            protected = replace(
                snapshot,
                inventory=(*snapshot.inventory, identify, unknown),
            )

            before = policy._home_deposit_candidate(unknown, protected)
            after = policy._home_deposit_candidate(
                replace(unknown, known=True, fully_known=True),
                replace(
                    protected,
                    inventory=tuple(
                        replace(item, known=True, fully_known=True)
                        if item.slot == unknown.slot else item
                        for item in protected.inventory
                    ),
                ),
            )

        self.assertEqual((before, after), (False, True))

    def test_recall_never_cross_town_but_teleport_still_does(self):
        """G2 regression: the real supply producer filters recall alone."""
        with TemporaryDirectory() as directory:
            policy = HengbotPolicy(
                home_disposal_state=self._state(Path(directory))
            )
            decisions, _ = replay_to_home_return(policy)
            snapshot = fixture_snapshot(39)
            without_teleport = replace(
                snapshot,
                inventory=tuple(
                    carried for carried in snapshot.inventory
                    if not carried.is_teleport_scroll
                ),
            )

            shortages = policy._cross_town_shortages(without_teleport)
            categories = tuple(category for category, _ in shortages)

        self.assertNotIn("recall", categories)
        self.assertIn("teleport", categories)
        self.assertFalse(any("town:cross-town" in reason for *_, reason in decisions))


if __name__ == "__main__":
    unittest.main()
