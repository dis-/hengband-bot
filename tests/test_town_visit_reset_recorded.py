"""Structure stage 3-2's rest: more state that ends with its town visit.

Owner 2026-11-03 「町の第3段 3-2 の残り」: the in-store watches, the town
order's operation, the dominated-disposal attempts, the Home disposal and the
Home procurement probe become town_visit.TownVisit fields, so the fresh-visit
reset ends them.

Recorded: the viewing bots' town-arrival checkpoints and visit journals
(tests/extract_town_visit_reset_fixture.py).  A restored checkpoint is the
policy just before the arrival's first decision, so the arrival here is the
production one: the recorded board through the public ``choose_key``.

Only n1a-1232's stale watches and operation are what the live bot held.  The
live logs show no arrival with a counter above zero, a step-4 operation, a
disposal or a probe, so those are DECLARED RECONSTRUCTED on the restored
checkpoint, before the arrival, in the shape their producers leave them.  The
recorded visit then decides as it did live; each case kept instead (before
slice 3-2) diverges on the row named in its test.  DECLARED WALL: the capture
holds no Home history file, so each policy's Home history is relocated to the
test's directory.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.model import parse_snapshot
from hengbot.policy_constants import STORE_STUCK_LIMIT
from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from replay_town_arrival import decisions, journal, restore
# Modules, not classes: a test class bound here would run again in this module.
import tests.test_idstaff_stockout_run_recorded as idstaff_run
from tests import test_input_executor as executor_pins
from town_work_corpus import replay_window


FIXTURES = Path(__file__).with_name("fixtures")
RESET = FIXTURES / "town-visit-reset-20261103"
# One attempt short of the limit: the next unchanged attempt ends the store.
ONE_SHORT = STORE_STUCK_LIMIT - 1


def board_of(row):
    return json.loads(row["line"] or row["inputs"][-1])


class ArrivalCase(executor_pins.ProductionHarness):
    def arrive(self, fixture):
        """The restored arrival: (policy, its journal rows, board suppliers)."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        visit = Path(directory.name) / "town-arrival"
        visit.mkdir()
        (visit / POLICY_FILE).write_bytes(
            lzma.decompress((fixture / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            lzma.decompress((fixture / "journal.jsonl.xz").read_bytes())))
        scratch = Path(directory.name) / "scratch"
        scratch.mkdir()
        policy = restore(visit, scratch)
        policy._home_disposal.relocate(scratch)  # The declared wall.
        rows = journal(visit)
        return policy, rows, list(decisions(policy, visit, scratch))

    def assert_decides_as_recorded(self, policy, rows, steps):
        result = replay_window("arrival", policy, iter(steps))
        self.assertIsNone(result.first_divergence)
        self.assertEqual(result.matched_rows, len(rows))

    def post(self, policy, row, key):
        """A walk's key through the production executor."""
        idstaff_run.IdstaffStockoutRunRecordedTest.post_dungeon_key(
            self, policy, board_of(row), key)

    def walk_on(self, policy, rows, steps):
        """Rows 0-1 of n1-a 12:32 (recover, then the walk Home): as recorded,
        and the walk goes through the production executor."""
        self.assertEqual(rows[1]["reason"], "shop:travel")
        for index in (0, 1):
            key = policy.choose_key(steps[index][1]())
            self.assertEqual((key, policy.last_reason),
                             (rows[index]["key"], rows[index]["reason"]))
            policy.confirm_key_posted(key)
        self.post(policy, rows[1], key)


class InStoreWatchesEndWithVisitTest(ArrivalCase):
    """Items 6-7: the purchase and sale no-progress watches."""

    def test_recorded_arrival_forgets_the_last_visits_watches(self):
        # n1-a 12:32: the checkpoint holds the previous visit's last attempts.
        policy, rows, steps = self.arrive(RESET / "n1a-1232")
        self.assertEqual(policy._last_buy_sig, ("j", 9129))
        self.assertEqual(policy._last_buy_progress_sig, ("j", 2, 9129))
        self.assertEqual(policy._last_sell_sig[0], "b")
        self.walk_on(policy, rows, steps)
        self.assertIsNone(policy._last_buy_sig)
        self.assertIsNone(policy._last_buy_progress_sig)
        self.assertIsNone(policy._last_sell_sig)

    def test_unchanged_buy_watch_of_the_last_visit_does_not_end_this_store(self):
        # n1-b 11:58 row 1 buys letter m at 13111 gold.  Kept, the watch made
        # this first attempt the limit's and the store was left unbought
        # (row 1: ESC, town-progress-invariant:continue-observed-shop).
        policy, rows, steps = self.arrive(RESET / "n1b-1158")
        policy._last_buy_sig = ("m", 13111)
        policy._store_stuck_count = ONE_SHORT
        self.assertEqual(rows[1]["key"], "pm2\r\r")
        self.assert_decides_as_recorded(policy, rows, steps)

    def test_buy_progress_watch_of_the_last_visit_does_not_end_this_store(self):
        # The same row: a registered buy of the same target and shortage last
        # visit.  Kept: the store was left unbought in the same way.
        policy, rows, steps = self.arrive(RESET / "n1b-1158")
        policy._last_buy_progress_sig = ("m", 2, 13999)
        policy._store_buy_no_progress_count = ONE_SHORT
        self.assert_decides_as_recorded(policy, rows, steps)

    def test_deposit_watch_of_the_last_visit_does_not_reject_this_deposit(self):
        # n1-a 12:05 rows 3-4 deposit letter i.  Kept, the watch rejected it:
        # row 3 went on to periodic:game-save instead of the deposit.
        policy, rows, steps = self.arrive(RESET / "n1a-1205")
        carried = next(item for item in board_of(rows[3])["inventory"] if item["slot"] == "i")
        policy._last_sell_sig = (
            "i", (carried["name"], carried["tval"], carried["sval"]),
            carried["count"], carried.get("charges", 0),
            len(board_of(rows[3])["inventory"]), board_of(rows[3])["player"]["gold"])
        policy._store_sell_stuck_count = ONE_SHORT
        self.assertEqual(rows[4]["reason"], "home:atomic-deposit")
        self.assert_decides_as_recorded(policy, rows, steps)


class TownOrderOperationEndsWithVisitTest(ArrivalCase):
    """Item 8: the town order's operation."""

    def test_recorded_arrival_forgets_the_last_visits_operation(self):
        policy, rows, steps = self.arrive(RESET / "n1a-1232")
        self.assertEqual(policy._town_order_operation, "normal-step5-required-supplies")
        self.assertEqual(policy._town_order_expected_observation, "departure-supplies-ready")
        self.assertEqual(rows[0]["reason"], "town:recover")
        key = policy.choose_key(steps[0][1]())
        self.assertEqual((key, policy.last_reason), (rows[0]["key"], rows[0]["reason"]))
        # Row 0 reaches no order step, so nothing bound the operation again.
        self.assertIsNone(policy._town_order_operation)
        self.assertIsNone(policy._town_order_expected_observation)

    def test_step4_of_the_last_visit_reports_no_bounty_removed_here(self):
        # The pack holds no bounty.  Kept, the step of the last visit reported
        # "bounty-removed" to this visit's decision for work it never did.
        policy, rows, steps = self.arrive(RESET / "n1b-1158")
        policy._town_order_operation = "normal-step4-bounty"
        policy._town_order_expected_observation = "bounty-removed"
        reported = []
        for index, (recorded, supply) in enumerate(steps):
            key = policy.choose_key(supply())
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]))
            reported.extend(getattr(policy, "_decision_observed_execution_effects", ()))
            if index == 0:
                self.post(policy, rows[0], key)
            policy.confirm_key_posted(key)
        self.assertNotIn("bounty-removed", {effect[2] for effect in reported})


class DominatedDisposalAttemptsEndWithVisitTest(ArrivalCase):
    """Items 9-10: the attempts of a dominated item's disposal.

    The target itself lives on: a disposal is not bound to a visit, only its
    attempts are.  The weapon goes to the Weapon Smith ("#") again.
    """

    def spare_weapon(self, rows):
        spare = next(item for item in board_of(rows[0])["inventory"] if item["slot"] == "t")
        return (spare["name"], spare["tval"], spare["sval"])

    def assert_shelves_are_tried_again(self, policy, steps):
        target = policy._pending_disposal_item
        for _recorded, supply in steps[:1]:
            policy.confirm_key_posted(policy.choose_key(supply()))
        self.assertEqual(policy._destroy_attempts, 0)
        self.assertEqual(policy._disposal_store_attempts, set())
        board = steps[1][1]()
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("\x1b`n#.", "shop:travel"))
        self.assertEqual(policy._pending_disposal_item, target)
        return key, board

    def test_spent_destroy_budget_of_the_last_visit_blocks_nothing_here(self):
        # Kept: row 1 town:blocked:dominated-item-destroy-failed.
        policy, rows, steps = self.arrive(RESET / "n1a-1232")
        policy._pending_disposal_item = self.spare_weapon(rows)
        policy._destroy_pending = True
        policy._destroy_attempts = STORE_STUCK_LIMIT
        self.assert_shelves_are_tried_again(policy, steps)

    def test_stores_tried_last_visit_are_tried_again(self):
        # Kept: the tried stores sent the weapon straight to destruction, whose
        # protection refused it and dropped the disposal (row 1 walked to the
        # Magic shop instead).
        policy, rows, steps = self.arrive(RESET / "n1a-1232")
        policy._pending_disposal_item = self.spare_weapon(rows)
        policy._disposal_store_attempts.update({1, 2})
        key, _board = self.assert_shelves_are_tried_again(policy, steps)
        self.post(policy, rows[1], key)


class HomeDisposalEndsWithVisitTest(ArrivalCase):
    """Item 11: the approved Home disposal in progress."""

    def queued(self, policy, rows, decision):
        ware = next(item for item in board_of(rows[2])["store"]["items"] if item["letter"] == "a")
        signature = (ware["name"], ware["tval"], ware["sval"])
        policy._home_disposal_pending = (signature, decision)
        policy._home_pending_item = signature
        policy._home_withdrawal_queued = True
        return signature

    def test_unfinished_destroy_of_the_last_visit_holds_no_home_take(self):
        # The state _home_disposal_home_key leaves when the trip interrupts it.
        # Kept: on row 3 the take is still queued (shop:approach back to Home
        # for a disposal nobody decided this visit).  The next pass plans it.
        policy, rows, steps = self.arrive(RESET / "n1a-1232")
        self.queued(policy, rows, "destroy")
        self.walk_on(policy, rows, steps)
        self.assertIsNone(policy._home_disposal_pending)
        self.assertIsNone(policy._home_pending_item)
        self.assertFalse(policy._home_withdrawal_queued)

    def test_recorded_visit_decides_as_if_no_disposal_was_left(self):
        policy, rows, steps = self.arrive(RESET / "n1a-1232")
        self.queued(policy, rows, "destroy")
        self.assert_decides_as_recorded(policy, rows, steps)

    def test_unfinished_sale_takes_its_identify_request_with_it(self):
        # The sale filed its request (_home_disposal_processing_key); with the
        # sale gone nothing owns it, and a latched request fails departure.
        policy, rows, steps = self.arrive(RESET / "n1a-1232")
        self.queued(policy, rows, "sell")
        policy._identification_need = "normal"
        policy.choose_key(steps[0][1]())
        self.assertIsNone(policy._identification_need)


class HomeProcurementProbeEndsWithVisitTest(ArrivalCase):
    """Item 12: the Home absence probe of a purchase."""

    def test_probe_of_the_last_visit_does_not_decline_this_visits_owner(self):
        # n1-b 12:03 row 2 binds the catalogue shortage at Home.  Kept, the
        # stale probe read as a probe in flight and declined the new owner:
        # home:identify-staff-reserve-unavailable, the take never queued.
        policy, rows, steps = self.arrive(RESET / "n1b-1203")
        policy._home_procurement_probe = (75, 61)
        self.assertEqual(rows[2]["reason"], "home:queue-catalogue-shortage")
        self.assert_decides_as_recorded(policy, rows, steps)
        self.assertIsNotNone(policy._home_pending_item)


if __name__ == "__main__":
    import unittest
    unittest.main()
