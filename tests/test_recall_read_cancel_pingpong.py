"""R2 class pins for the town recall read/cancel ping-pong (2026-09-25 14:52).

Live: ``town:recall-to-alt-dungeon`` read a Word of Recall, the next decision's
``town:cancel-unready-recall`` read another one to cancel it, the town bought
the two scrolls back, and the pair repeated nine times in two minutes until the
scrolls ran out (tests/test_recall_read_cancel_pingpong_recorded.py pins the
recorded boards).  The class: the read point and the canceller judged
readiness on different boards, and nothing bounded a read -> cancel -> read
sequence within one town visit.

These scenarios are constructed.  One town visit is driven through the two real
producers -- the ordinary departure read point (``_town_special_key``) and the
canceller (``_town_cancel_unsafe_recall_key``) -- over three boards:

  A  departure ready: the read point reads the recall;
  B  the board after that read (one scroll consumed, recall armed) with one
     departure leaf made unmet;
  C  the board after a cancel (the scroll stock bought back, recall disarmed)
     with the leaf repaired: departure is ready again.

For every leaf of ``_recall_town_departure_conjuncts`` the visit must not
contain read -> cancel -> read.  Seams: the leaf is made unmet by overriding its
value in the conjunct map (both producers read that one map), and the
optimizer verdict the constructed character has no catalogue for is answered
ready (``_equipment_departure_ready``), as the existing town departure tests
do.  The character carries the abilities and escape kit its landing requires.
"""

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
from dataclasses import replace
import unittest
from unittest.mock import patch

from hengbot.model import (
    DUNGEON_ANGBAND,
    PLAYER_CLASS_WARRIOR,
    Position,
    STORE_HOME,
    SV_FLASK_OIL,
    SV_LITE_LANTERN,
    SV_POTION_CURE_CRITICAL,
    SV_SCROLL_TELEPORT,
    SV_SCROLL_WORD_OF_RECALL,
    Snapshot,
    TVAL_FLASK,
    TVAL_FOOD,
    TVAL_LITE,
    TVAL_POTION,
    TVAL_SCROLL,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import (
    MIN_FREE_PACK_SLOTS,
    MIN_TERMINAL_FREE_PACK_SLOTS,
    PACK_CAPACITY,
    POLICY_FINAL_STOP_REASONS,
)
from policy_fixtures import grid, item, player


RECALL_STOCK = 6
READ_TURN = 1000
CANCEL_LEAVES = {
    "free_pack_slots_ready": "pack-too-full",
    "combat_weapon_ready": "weapon-not-ready",
    "equipment_departure_ready": "deep-loadout-unconfirmed",
}
DEEP_LANDING = 25  # > 20: the canceller also guards the deep loadout leaf
# Every ability the depth bands up to the landing require, and a full escape
# kit, so the constructed recall destination is safe and enterable as is.
ABILITIES = frozenset({"free_action", "resist_conf", "resist_fire"})
TELEPORT = 15
CRITICAL = 12
CONTRADICTION = "town:blocked:recall-readiness-contradiction"


class RecallReadCancelClassTest(unittest.TestCase):
    @staticmethod
    def _strict_supplies(*, recall, teleport, critical):
        # The departure kit of tests/policy_shop_fixture.py's strict supplies.
        return [
            item("f", TVAL_FOOD, 35, count=5),
            item("o", TVAL_FLASK, SV_FLASK_OIL, count=5, fuel=500),
            item("r", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=recall),
            item("t", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=teleport),
            item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=critical),
        ]

    @staticmethod
    def _lantern():
        return item(
            "light", TVAL_LITE, SV_LITE_LANTERN, fuel=5000, is_equipment=True
        )

    def _board(self, *, recall, recalling, turn, filler=0):
        inventory = self._strict_supplies(
            recall=recall, teleport=TELEPORT, critical=CRITICAL
        )
        inventory += [
            item(chr(ord("A") + index), 5, index, name=f"junk-{index}")
            for index in range(filler)
        ]
        base = Snapshot(
            player(10, 10, class_id=PLAYER_CLASS_WARRIOR, abilities=ABILITIES),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=inventory,
            equipment=[self._lantern()],
            recall_dungeon_id=DUNGEON_ANGBAND,
            dungeon_recall_depths={DUNGEON_ANGBAND: DEEP_LANDING},
            yeek_cave_conquered=True,
            angband_recall_unlocked=True,
        )
        return replace(
            base,
            turn=turn,
            player=replace(base.player, recalling=recalling),
        )

    def _policy(self, board):
        policy = HengbotPolicy()
        policy._char_dump_done_this_visit = True
        policy.prime(board)
        policy._town_store_attempted[STORE_HOME] = board.turn
        return policy

    def _visit(self, leaf, *, filler=0, certify=False):
        """Drive A -> B -> C; return the reasons and keys in order."""
        board_a = self._board(recall=RECALL_STOCK, recalling=False, turn=READ_TURN, filler=filler)
        board_b = self._board(recall=RECALL_STOCK - 1, recalling=True, turn=READ_TURN + 10, filler=filler)
        board_c = self._board(recall=RECALL_STOCK, recalling=False, turn=READ_TURN + 20, filler=filler)
        policy = self._policy(board_a)
        if certify:
            # The terminal town fallback's four-slot certificate for board A.
            policy._terminal_pack_space_signature = (
                policy._town_pack_space_signature(board_a)
            )
        unmet = {"leaf": None}
        real_conjuncts = policy._recall_town_departure_conjuncts

        def conjuncts(board):
            values = real_conjuncts(board)
            if unmet["leaf"] is not None:
                values[unmet["leaf"]] = False
            return values

        emitted = []
        with patch.object(
            policy, "_recall_town_departure_conjuncts", side_effect=conjuncts
        ), patch.object(
            policy, "_equipment_departure_ready", return_value=True
        ):
            key = policy._town_special_key(board_a)
            emitted.append((key, policy.last_reason))
            unmet["leaf"] = leaf
            key = policy._town_cancel_unsafe_recall_key(board_b)
            emitted.append((key, policy.last_reason if key is not None else None))
            cancelled = policy.last_reason == "town:cancel-unready-recall" and key is not None
            if cancelled:
                unmet["leaf"] = None
                key = policy._town_special_key(board_c)
                emitted.append((key, policy.last_reason))
        return emitted

    @staticmethod
    def _is_read(entry):
        key, reason = entry
        return key is not None and (reason or "").startswith("town:recall-to-")

    def _assert_no_read_cancel_read(self, emitted):
        reasons = [reason for _key, reason in emitted]
        for first in range(len(emitted)):
            if not self._is_read(emitted[first]):
                continue
            for middle in range(first + 1, len(emitted)):
                if reasons[middle] != "town:cancel-unready-recall":
                    continue
                self.assertFalse(
                    any(self._is_read(entry) for entry in emitted[middle + 1:]),
                    emitted,
                )

    def test_constructed_visit_reads_on_the_ready_board(self):
        emitted = self._visit(None)
        self.assertEqual(emitted[0], ("rra", "town:recall-to-angband"))

    def test_r2_no_read_cancel_read_for_any_unmet_departure_leaf(self):
        policy = self._policy(
            self._board(recall=RECALL_STOCK, recalling=False, turn=READ_TURN)
        )
        leaves = list(policy._recall_town_departure_conjuncts(
            self._board(recall=RECALL_STOCK, recalling=False, turn=READ_TURN)
        ))
        self.assertTrue(set(CANCEL_LEAVES) <= set(leaves))
        for leaf in leaves:
            with self.subTest(leaf=leaf):
                emitted = self._visit(leaf)
                self.assertEqual(emitted[0], ("rra", "town:recall-to-angband"))
                self._assert_no_read_cancel_read(emitted)
                if leaf in CANCEL_LEAVES:
                    # The leaf changed after the read: one cancel, then the
                    # visit stops visibly instead of reading again.
                    self.assertEqual(
                        emitted[1][1], "town:cancel-unready-recall"
                    )
                    self.assertEqual(emitted[2][1], CONTRADICTION)
                    self.assertIn(CONTRADICTION, POLICY_FINAL_STOP_REASONS)
                else:
                    # The canceller does not act on this leaf: the armed
                    # recall stays, so the visit cannot alternate.
                    self.assertEqual(emitted[1], (None, None))

    def test_r2_the_read_alone_never_arms_the_cancel(self):
        """Incident shape: 19 items, the four-slot certificate, nothing else.

        The read consumes one scroll of a stack the certificate signs.  The
        canceller judges the read point's conjunct map on the read's own
        board, so it has no blocker and leaves the recall armed.
        """
        filler = PACK_CAPACITY - MIN_TERMINAL_FREE_PACK_SLOTS - len(
            self._strict_supplies(
                recall=RECALL_STOCK, teleport=TELEPORT, critical=CRITICAL
            )
        )
        board_a = self._board(
            recall=RECALL_STOCK, recalling=False, turn=READ_TURN, filler=filler
        )
        free = PACK_CAPACITY - len(board_a.inventory)
        self.assertEqual(free, MIN_TERMINAL_FREE_PACK_SLOTS)
        self.assertLess(free, MIN_FREE_PACK_SLOTS)
        emitted = self._visit(None, filler=filler, certify=True)
        self.assertEqual(emitted[0], ("rra", "town:recall-to-angband"))
        self.assertEqual(emitted[1], (None, None))


if __name__ == "__main__":
    unittest.main()
