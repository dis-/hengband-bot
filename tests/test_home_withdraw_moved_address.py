"""Class pins: a Home take that moved other owners' addresses is not a failure.

Failure mode (2026-09-25 17:30 stop, tests/test_home_withdraw_failed_stock_
present_recorded.py): a confirmed Home take at shelf index i shortens the
addressable prefix of the current ``~9`` catalogue to i
(``_confirm_home_withdrawal_address``) and only asks for a fresh scan when
*every* other owner lies at or beyond i.  With owners on both sides (an
earlier potion, a later shovel), the later owner stayed catalogued but
unaddressable, and the atomic composer read that as
``home:atomic-withdraw-target-unobserved``: it deferred the owner as an
``unobserved-home-withdrawal`` (and counted a digger failure) although no take
of it was ever posted -- after one deferred retry, the Home-first procurement
gate stopped the run with ``town:blocked:home-withdraw-failed-stock-present``.
The pending item whose own take had just been confirmed was deferred the same
way, as if its successful withdrawal had failed.

Fixed class, for every withdrawal owner the composer serves (pending item,
queued batch, Home errand):
- an owner catalogued at or beyond the shortened prefix earns a fresh complete
  scan (knowledge invalidated, ``home:await-fresh-knowledge``); it is neither
  deferred nor counted as a failure, and after the rescan it is taken;
- the pending item whose take was confirmed is released as complete: never
  deferred, never taken again, never a failure -- unless a new request queues
  the same identity again; other work queued beside it (an ammo top-up raises
  the shared ``_home_withdrawal_queued``) leaves that take complete;
- a genuinely failing withdrawal still fails: an owner absent from the fresh
  complete catalogue is still ``target-unobserved`` (deferred), and a posted
  take without an inventory gain still reaches the gate's stop
  (test_policy_shop: test_pin_vacuity_observed_terminal_withdraw_failure_
  records_procurement, test_terminal_failure_viable_deferred_stock_is_refused_
  by_evaluate_consumer; test_policy_home: test_restore_list_does_not_steal_
  unobserved_digger_failure).

Each take is composed at the Home entrance, posted, and observed through the
public ``choose_key`` on the next outside board, which -- standing on the
entrance, as recorded -- also runs the composer for the next owner.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import unittest
from dataclasses import replace

from policy_fixtures import grid, item, player, store_item
from hengbot.home_errand import HomeErrandRequest
from hengbot.model import (
    PLAYER_CLASS_WARRIOR,
    STORE_HOME,
    SV_BOW_LIGHT_XBOW,
    SV_DIGGING_SHOVEL,
    SV_SCROLL_DETECT_TREASURE,
    TVAL_BOLT,
    TVAL_BOW,
    TVAL_DIGGING,
    TVAL_POTION,
    TVAL_SCROLL,
    Position,
    Snapshot,
)
from hengbot.policy import HengbotPolicy


PAGE_SIZE = 12
EARLIER, TAKEN, LATER, BOLTS = 0, 5, 15, 18
BOLT_NAME = "plain bolts (1d5) (+0,+0)"
LAUNCHER = item(
    "bow", TVAL_BOW, SV_BOW_LIGHT_XBOW, name="light crossbow", is_equipment=True,
)
ENTRANCE = Position(45, 123)
BESIDE = Position(45, 122)
STEP_KEYS = set("12346789")


def home_bolts(count):
    return store_item(
        "b", TVAL_BOLT, 1, count=count, name=BOLT_NAME,
        damage_dice_num=1, damage_dice_sides=5,
        exported_fields=frozenset({
            "aware", "known", "fully_known", "pval", "fuel", "timeout",
            "is_ego", "is_artifact", "is_cursed", "is_broken",
            "inscription", "to_h", "to_d", "to_a", "ac",
            "damage_dice", "known_flags",
        }),
    )


def carried_bolts(count, slot="q"):
    return item(
        slot, TVAL_BOLT, 1, count=count, name=BOLT_NAME,
        fully_known=True, damage_dice_num=1, damage_dice_sides=5,
    )


def wares(*, taken_count=27, later_present=True, bolts=None):
    """A 20-slot ``~9`` catalogue: potion at 0, scroll at 5, shovel at 15.

    With ``bolts``, plain bolts that stack with the carried ones sit at 18.
    """
    shelf = [
        store_item(str(index), TVAL_POTION, 900 + index, name=f"home potion {index}")
        for index in range(20)
    ]
    shelf[EARLIER] = store_item(
        "e", TVAL_POTION, 37, count=3, name="earlier cure potion"
    )
    shelf[TAKEN] = store_item(
        "s", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, count=taken_count,
        name="treasure detection scroll",
    )
    shelf[LATER] = store_item(
        "x", TVAL_DIGGING, SV_DIGGING_SHOVEL, count=2,
        name="later shovel", is_equipment=True,
    )
    if bolts is not None:
        shelf[BOLTS] = home_bolts(bolts)
    if not later_present:
        del shelf[LATER]
    return tuple(shelf)


def board(inventory=(), *, turn, at=ENTRANCE):
    return Snapshot(
        player(at.y, at.x, class_id=PLAYER_CLASS_WARRIOR),
        {
            ENTRANCE: replace(grid(ENTRANCE.y, ENTRANCE.x), store_number=STORE_HOME),
            BESIDE: grid(BESIDE.y, BESIDE.x),
        },
        [],
        turn=turn,
        floor_key=(0, 0, 0),
        town_flag=True,
        inventory=list(inventory),
        store=None,
    )


def carried(stored, count, slot="a"):
    return item(
        slot, stored.tval, stored.sval, count=count, name=stored.name,
        known=True, is_equipment=stored.is_equipment,
    )


class HomeWithdrawMovedAddressTest(unittest.TestCase):
    def setUp(self):
        self.shelf = wares()
        self.policy = HengbotPolicy()
        # As recorded: preparing a mining run without its digging tools, so
        # carried-item processing (which would release a withdrawn pending
        # item) is held back and the composer meets the pending item again.
        self.policy._fundraising_mode = "prepare"
        # Already in town (the visit's fresh-town reset is behind us).
        self.policy.prime(board(turn=5552400, at=BESIDE))
        self.policy.consume_home_knowledge(self.shelf)
        self.policy._home_page_size = PAGE_SIZE
        self.policy._shopping_approach_store_type = STORE_HOME
        self.earlier = self.policy._item_signature(self.shelf[EARLIER])
        self.taken = self.policy._item_signature(self.shelf[TAKEN])
        self.later = self.policy._item_signature(self.shelf[LATER])

    def take(self, stored, *, turn=5552439, observe_at=ENTRANCE):
        """Compose and post one take, then decide on its confirming board."""
        policy = self.policy
        key = policy._atomic_home_withdraw_key(board(turn=turn), ENTRANCE)
        self.assertEqual(policy.last_reason, "home:atomic-withdraw")
        policy.confirm_key_posted(key)
        decision = policy.choose_key(
            board([carried(stored, 1)], turn=turn + 5, at=observe_at)
        )
        return key, decision, policy.last_reason

    def assert_nothing_failed(self):
        policy = self.policy
        self.assertEqual(policy._deferred_home_items, set())
        self.assertEqual(policy._digger_home_withdraw_failures, 0)
        self.assertIsNone(policy._home_procurement_withdraw_failure)

    def assert_rescan_requested(self):
        policy = self.policy
        self.assertFalse(policy._home_knowledge_current)
        self.assertTrue(policy._home_knowledge_invalidated)

    def rescan_and_compose(self, shelf, *, turn=5552460):
        policy = self.policy
        policy.consume_home_knowledge(shelf)
        policy._shopping_approach_store_type = STORE_HOME
        policy._store_entrance_step_off = None
        key = policy._atomic_home_withdraw_key(board(turn=turn), ENTRANCE)
        return key, policy._home_atomic_withdraw_telemetry

    # ------------------------------------------------------------ the class
    def test_pending_take_with_owners_on_both_sides_rescans_then_takes_later(self):
        """The incident's shape: pending scroll taken, shovel later, potion earlier."""
        policy = self.policy
        policy._home_pending_item = self.taken
        policy._home_pending_quantity = 1
        policy._home_pending_batch = [self.later, self.earlier]
        policy._home_pending_quantities[self.later] = 2

        taken_key, decision, reason = self.take(self.shelf[TAKEN])

        self.assertEqual(taken_key, "5pf1\r\x1b")
        # Recorded: '6' town:entrance-step-off:home:atomic-withdraw-target-
        # unobserved, deferring the scroll, then the shovel.  Fixed: the
        # shovel's address moved, so Home is entered for a fresh scan.
        self.assertEqual((decision, reason), ("5", "shop:travel:await-entry"))
        self.assert_rescan_requested()
        self.assertIsNone(policy._home_pending_item)
        self.assertEqual(policy._home_pending_batch, [self.later, self.earlier])
        self.assert_nothing_failed()

        # The fresh scan still holds the rest of the scroll stack; it is not
        # taken again.  The shovel is taken at its real address.
        key, telemetry = self.rescan_and_compose(wares(taken_count=26))
        self.assertEqual(telemetry["selected_signature"], list(self.later))
        self.assertEqual(
            (telemetry["resolved_index"], telemetry["resolved_page"],
             telemetry["resolved_letter"]),
            (LATER, 1, "d"),
        )
        self.assertEqual(key, "5 pd2\r\x1b")
        self.assert_nothing_failed()

    def test_batch_owner_beyond_the_prefix_rescans_instead_of_failing(self):
        policy = self.policy
        policy._home_pending_batch = [self.taken, self.later, self.earlier]
        policy._home_pending_quantities[self.taken] = 1

        taken_key, decision, reason = self.take(self.shelf[TAKEN])

        self.assertEqual(taken_key, "5pf1\r\x1b")
        self.assertEqual((decision, reason), ("5", "shop:travel:await-entry"))
        self.assert_rescan_requested()
        self.assertEqual(policy._home_pending_batch, [self.later, self.earlier])
        self.assert_nothing_failed()
        key, telemetry = self.rescan_and_compose(wares(taken_count=26))
        self.assertEqual(telemetry["selected_signature"], list(self.later))
        self.assertEqual(key, "5 pd1\r\x1b")

    def test_errand_target_beyond_the_prefix_rescans_instead_of_failing(self):
        policy = self.policy
        policy._home_pending_batch = [self.taken]
        policy._home_pending_quantities[self.taken] = 1
        self.take(self.shelf[TAKEN], observe_at=BESIDE)
        self.assertEqual(policy._home_knowledge_valid_before, TAKEN)
        self.assertIsNone(policy._home_atomic_withdraw_pending)
        policy._file_home_errand(
            board(turn=5552445),
            HomeErrandRequest(self.later, 1, "home-catalog", "identification-catalog"),
            knowledge_current=policy._home_knowledge_current,
        )
        self.assertTrue(policy._home_errand.active)
        policy._shopping_approach_store_type = STORE_HOME
        policy._store_entrance_step_off = None

        self.assertIsNone(
            policy._atomic_home_withdraw_key(board(turn=5552450), ENTRANCE)
        )

        self.assertEqual(
            policy.last_reason,
            policy._home_errand.reason("await-fresh-knowledge"),
        )
        self.assert_rescan_requested()
        self.assert_nothing_failed()
        key, telemetry = self.rescan_and_compose(wares(taken_count=26))
        self.assertEqual(telemetry["selected_signature"], list(self.later))
        self.assertEqual(telemetry["selecting_branch"], "home-errand")

    def test_confirmed_pending_take_alone_is_released_as_complete(self):
        """A digger's confirmed take is not a digger failure or a deferral."""
        policy = self.policy
        policy._home_pending_item = self.later
        policy._home_pending_quantity = 1

        taken_key, decision, reason = self.take(self.shelf[LATER])

        self.assertEqual(taken_key, "5 pd1\r\x1b")
        self.assertIn(decision, STEP_KEYS)
        self.assertEqual(
            reason, "town:entrance-step-off:home:atomic-withdraw-complete"
        )
        self.assertIsNone(policy._home_pending_item)
        self.assert_nothing_failed()

    def test_ammo_top_up_beside_a_confirmed_take_takes_the_ammo(self):
        """gpt-6-sol P2: queueing ammo raises the shared queued flag.

        The scroll's take is confirmed with 26 left in Home; the ammo top-up
        then queues the Home bolts behind it (``_queue_home_ammo_top_up``
        sets ``_home_withdrawal_queued``).  That is not a request for more
        scrolls: the bolts are taken, the scroll is not taken again.
        """
        policy = self.policy
        policy.consume_home_knowledge(wares(bolts=80))
        policy._home_pending_item = self.taken
        policy._home_pending_quantity = 1
        bolts = policy._item_signature(home_bolts(80))
        # Confirmed off the entrance: the composer has not met it yet.
        self.take(self.shelf[TAKEN], observe_at=BESIDE)
        self.assertEqual(policy._home_pending_item, self.taken)
        policy.consume_home_knowledge(wares(taken_count=26, bolts=80))
        armed = replace(
            board(
                [carried(self.shelf[TAKEN], 1, slot="a"), carried_bolts(10)],
                turn=5552455,
            ),
            equipment=[LAUNCHER],
        )

        self.assertTrue(policy._queue_home_ammo_top_up(armed))
        self.assertTrue(policy._home_withdrawal_queued)
        self.assertEqual(policy._home_pending_item, self.taken)
        self.assertEqual(policy._home_pending_batch, [bolts])
        policy._shopping_approach_store_type = STORE_HOME
        policy._store_entrance_step_off = None
        key = policy._atomic_home_withdraw_key(armed, ENTRANCE)

        telemetry = policy._home_atomic_withdraw_telemetry
        self.assertEqual(telemetry["selected_signature"], list(bolts))
        self.assertEqual(telemetry["selecting_branch"], "home-pending-batch")
        self.assertEqual(key, "5 pg80\r\x1b")
        self.assert_nothing_failed()

    def test_same_identity_requeued_is_withdrawal_work_again(self):
        """A new ammo request for the confirmed pending bolts reopens them."""
        policy = self.policy
        policy.consume_home_knowledge(wares(bolts=99))
        bolts = policy._item_signature(home_bolts(99))
        armed = replace(
            board([carried_bolts(10)], turn=5552439), equipment=[LAUNCHER]
        )
        self.assertTrue(policy._queue_home_ammo_top_up(armed))
        self.assertEqual(policy._home_pending_item, bolts)
        key = policy._atomic_home_withdraw_key(armed, ENTRANCE)
        self.assertEqual(key, "5 pg89\r\x1b")
        policy.confirm_key_posted(key)
        policy.choose_key(replace(
            board([carried_bolts(99)], turn=5552444, at=BESIDE),
            equipment=[LAUNCHER],
        ))
        self.assertEqual(policy._home_pending_take_confirmed, bolts)
        # Shots spent; the same Home stack (10 left) is requested again.
        policy.consume_home_knowledge(wares(bolts=10))
        spent = replace(
            board([carried_bolts(50)], turn=5552460), equipment=[LAUNCHER]
        )
        self.assertTrue(policy._queue_home_ammo_top_up(spent))
        self.assertIsNone(policy._home_pending_take_confirmed)
        policy._shopping_approach_store_type = STORE_HOME
        policy._store_entrance_step_off = None

        key = policy._atomic_home_withdraw_key(spent, ENTRANCE)

        self.assertEqual(key, "5 pg10\r\x1b")
        self.assertEqual(
            policy._home_atomic_withdraw_telemetry["selected_signature"],
            list(bolts),
        )

    def test_unrequeued_pending_item_is_not_taken_again_after_a_rescan(self):
        policy = self.policy
        policy._home_pending_item = self.taken
        policy._home_pending_quantity = 1
        policy._home_pending_batch = [self.earlier]
        self.take(self.shelf[TAKEN], observe_at=BESIDE)
        self.assertEqual(policy._home_pending_item, self.taken)

        key, telemetry = self.rescan_and_compose(wares(taken_count=26))

        self.assertEqual(key, "5pa1\r\x1b")
        self.assertEqual(telemetry["selected_signature"], list(self.earlier))
        self.assert_nothing_failed()

    # ------------------------------------------------------ genuine failure
    def test_owner_absent_from_the_fresh_catalogue_is_still_unobserved(self):
        policy = self.policy
        policy._home_pending_batch = [self.taken, self.later, self.earlier]
        policy._home_pending_quantities[self.taken] = 1
        self.take(self.shelf[TAKEN])
        self.assert_rescan_requested()
        # The fresh complete scan no longer holds the shovel at all.
        policy.consume_home_knowledge(wares(taken_count=26, later_present=False))
        policy._shopping_approach_store_type = STORE_HOME
        policy._store_entrance_step_off = None

        step = policy._atomic_home_withdraw_key(board(turn=5552460), ENTRANCE)

        self.assertIn(step, STEP_KEYS)
        self.assertEqual(
            policy.last_reason,
            "town:entrance-step-off:home:atomic-withdraw-target-unobserved",
        )
        self.assertIn(self.later, policy._deferred_home_items)
        self.assertEqual(
            policy._deferred_home_item_sites[self.later],
            "unobserved-home-withdrawal",
        )


if __name__ == "__main__":
    unittest.main()
