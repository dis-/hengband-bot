"""Captured E1 boards pin unavailable random-teleport suppression work."""
from __future__ import annotations

import tests  # noqa: F401 -- isolate runtime files for bare module runs
import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hengbot.model import DUNGEON_YEEK_CAVE, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.equipment_optimizer import Loadout, TR_TELEPORT, current_loadout
from hengbot.item_reservation import reserved_item_command, reservation_verdict
from policy_fixtures import (
    seed_confirmed_loadout, set_completed_equipment_optimization, store_item,
)

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "tp-suppress-e1-20261014.jsonl.gz"
BOUNDARIES = FIXTURES / "tp-suppress-e1-20261014.boundaries.json"
FIXTURE_SHA256 = "c277ec93add3c184aad9af5b3dc23618016601f4a3486ce54cc7964a5234e8df"
BOUNDARIES_SHA256 = "57c380b0215aa9bc7c29d19b6e9667e535bfbb242041024ab6d154010df54fcb"


def _boards():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
    assert hashlib.sha256(BOUNDARIES.read_bytes()).hexdigest() == BOUNDARIES_SHA256
    boundaries = json.loads(BOUNDARIES.read_text(encoding="utf-8"))
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        raw = [json.loads(line) for line in stream]
    return boundaries, [parse_snapshot(row, {}) for row in raw]


def _selected_preparation(policy, snapshot, owned):
    current = current_loadout(policy._equipment_catalog.items)
    # DECLARED CONSTRUCTED optimizer result: the archived state stream does not
    # include the private optimizer result. This frame pins the selected target
    # through the shared optimizer fixture while exercising production policy.
    result = set_completed_equipment_optimization(
        policy,
        best_loadout=Loadout((("main_hand", owned),), "one_handed"),
    )(snapshot).result
    return SimpleNamespace(
        current=current,
        result=result,
        transaction=None,
        blockers=("pending-random-teleport-suppression",),
        ready=False,
    )


class RandomTeleportSuppressionIncidentTest(unittest.TestCase):
    def test_captured_rows_pin_the_two_original_stop_decisions(self):
        boundaries, boards = _boards()
        self.assertEqual(
            [board.turn for board in boards], boundaries["fixture_turns"]
        )
        self.assertEqual(
            [(row["key"], row["reason"]) for row in boundaries["records"]],
            [
                ("5", "town:blocked:owner-retired-burst"),
                ("5", "town:blocked:departure-unsatisfiable"),
            ],
        )
        self.assertTrue(all(
            row["departure_failed"] == ["equipment_departure_ready"]
            and row["equipment_blockers"]
            == ["pending-random-teleport-suppression"]
            and row["transaction_actions"] == 0
            and row["equipment_transaction"] == {
                "context": None, "entry_blocker": "no-session"
            }
            for row in boundaries["records"]
        ))

    def test_identification_candidate_alone_does_not_own_the_captured_pack_item(self):
        _boundaries, boards = _boards()
        snapshot = boards[0]
        policy = HengbotPolicy()
        policy._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        target = next(
            owned for owned in policy._equipment_catalog.items
            if owned.origin == "pack"
            and (owned.item.tval, owned.item.sval) == (23, 14)
        )
        self.assertEqual(target.item.slot, "p")
        self.assertTrue(target.item.known)
        self.assertFalse(target.item.fully_known)
        # DECLARED CONSTRUCTED intent: the capture records the optimizer's
        # preserve reason, not the policy's private reservation view.
        policy._identification_candidate = policy._item_signature(target.item)

        verdict = reservation_verdict(
            policy, snapshot, target.item, "equipment-txn", "inscribe"
        )

        self.assertIsNone(verdict.owner)
        self.assertEqual(
            reserved_item_command(
                policy, snapshot, "inscribe", target.item, "equipment-txn"
            ),
            "{p",
        )

    def test_captured_deferred_candidates_can_depart_on_the_current_kit_once(self):
        boundaries, boards = _boards()
        for index, (record, snapshot) in enumerate(
            zip(boundaries["records"], boards, strict=True)
        ):
            with self.subTest(capture=record["capture"]), TemporaryDirectory() as raw:
                policy = HengbotPolicy()
                policy._confirmed_loadout_path = Path(raw) / "confirmed.json"
                policy._equipment_optimizer_input_key = ("captured", snapshot.turn)
                policy._equipment_catalog.refresh_carried(
                    snapshot.inventory, snapshot.equipment
                )
                home_signature = next(
                    value for value in record["deferred_home_item_signatures"]
                    if value[1:] == [37, 16]
                )
                # DECLARED CONSTRUCTED Home catalogue entry: the state row
                # records the deferred signature, but not the complete
                # optimizer catalog object needed by this production method.
                home_item = store_item(
                    "b", 37, 16, name=home_signature[0], known=True,
                    fully_known=False, is_equipment=True, is_artifact=True,
                    known_flags=frozenset({TR_TELEPORT}),
                )
                policy._equipment_catalog.complete_home_scan([home_item])
                target = next(
                    owned for owned in policy._equipment_catalog.items
                    if owned.origin == "home"
                )
                policy._deferred_home_items.add(
                    policy._item_signature(home_item)
                )
                preparation = _selected_preparation(policy, snapshot, target)
                policy._equipment_optimization_preparation = preparation
                policy._equipment_optional_failure_pending = None
                policy._char_dump_done_this_visit = True
                policy._target_dungeon_id = DUNGEON_YEEK_CAVE
                policy._deepest_level = 19
                seed_confirmed_loadout(policy, snapshot)
                with patch.object(
                    policy,
                    "_prepare_equipment_optimization",
                    return_value=preparation,
                ), patch.object(
                    policy,
                    "_current_worn_loadout_confirmed",
                    return_value=True,
                ), patch.object(
                    policy,
                    "_safe_optional_equipment_failure_departure",
                    return_value=False,
                ):
                    self.assertIsNone(
                        policy._town_random_teleport_suppression_key(snapshot)
                    )
                    self.assertFalse(
                        policy._random_teleport_suppression_actionable(
                            snapshot, preparation
                        )
                    )
                    # The complete policy gate still checks all destination
                    # abilities; only the optional suppression blocker is
                    # discharged for this constructed captured state.
                    self.assertTrue(
                        policy._equipment_departure_ready(
                            snapshot, destination_depth=19
                        )
                    )
                    key = policy._town_special_key(snapshot)
                    self.assertEqual(
                        key, ("rhb", "rfb")[index],
                        (policy.last_reason,
                         policy._town_recall_destination(snapshot),
                         policy._departure_block_state(snapshot)["failed"]),
                    )
                    self.assertEqual(
                        policy.last_reason, "town:recall-to-yeek-cave"
                    )
                    self.assertFalse(
                        policy._departure_block_state(snapshot)["failed"]
                    )
                pending = policy._equipment_optional_failure_pending
                self.assertIsNotNone(pending)
                self.assertEqual(
                    pending["reason"],
                    "random-teleport-suppression-unactionable-current-loadout",
                )
                self.assertFalse(pending["posted"])
                # A posted dungeon-entry key settles one record; a duplicate
                # observer call cannot write a second record for the visit.
                policy._confirm_optional_equipment_failure_departure(
                    snapshot, key
                )
                posted = policy._equipment_optional_failure_departure
                self.assertIsNotNone(posted)
                self.assertTrue(posted["posted"])
                self.assertIsNone(policy._equipment_optional_failure_pending)
                policy._confirm_optional_equipment_failure_departure(
                    snapshot, key
                )
                self.assertEqual(policy._equipment_optional_failure_departure, posted)


if __name__ == "__main__":
    unittest.main()
