"""The *Destruction* means is one fact (hengbot.destruction_means) read by six named combinations.

Whole-bot maintainability review 2026-11-16 (R1, stage 2), behaviour-preserving: each reader keeps
the answer it gave before (main a44f4593e7), the record-only observer ``cross-rule:destruction-means``
logs a board where the readers disagree without changing the decision, and
scripts/destruction_means_lint.py fails on a new read of the kind outside the fact.

Recorded: the n1-a life-525 21:05:39 town-arrival checkpoint (tests/fixtures/n1a-525-departure-1115,
a Lv40 Warrior, device skill 32, twelve charged staves of *Destruction* in the Home), row 6's board
through the public choose_key.

DECLARED CONSTRUCTED:
* ``variant``: row 6's board with the pack, the device skill, the stun, the class and the town flag
  named per case; the absorbed staff's charges (me_capability.replacing_charges) are given per case,
  for the old and the new readings alike.
* ``_old_*``: the six readings as main a44f4593e7 wrote them, the reference the fact must equal.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import itertools
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import cross_rules, destruction_means, destruction_use, me_capability
from hengbot.model import (
    SV_SCROLL_STAR_DESTRUCTION, SV_STAFF_DESTRUCTION, TVAL_SCROLL, TVAL_STAFF, InventoryItem,
)
from hengbot.policy_constants import DESTRUCTION_USES_PER_STEP, PLAYER_CLASS_BERSERKER
from support.town_arrival_fixture import load

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import destruction_means_lint  # noqa: E402

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-525-departure-1115"


# -- main a44f4593e7's readings (the reference) ----------------------------------------------

def _old_reliable(snapshot):
    return destruction_use.staff_success(snapshot.player, 50) >= me_capability.RELIABLE_MIN_SUCCESS


def _old_charged(policy, items):
    return next((item for item in items if policy._is_destruction_staff(item) and item.known
                 and item.charges > 0), None)


def _old_home(policy, snapshot):
    return next(iter(destruction_use.staff_home_items(policy, snapshot)), None)


def _old_holds_means(policy, snapshot):
    return (me_capability.replacing_charges(policy, snapshot, destruction_use.STAFF) > 0
            or (_old_reliable(snapshot) and _old_charged(policy, snapshot.inventory) is not None)
            or (_old_reliable(snapshot) and _old_home(policy, snapshot) is not None))


def _old_total_uses(policy, snapshot):
    def carried(item):
        if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_STAR_DESTRUCTION:
            return max(0, item.count)
        if item.tval == TVAL_STAFF and item.sval == SV_STAFF_DESTRUCTION:
            return policy._stack_charges(item)
        return 0
    return sum(carried(item) for item in snapshot.inventory) + me_capability.replacing_charges(
        policy, snapshot, (TVAL_STAFF, SV_STAFF_DESTRUCTION))


def _old_owns(policy, snapshot):
    return (_old_charged(policy, snapshot.inventory) is not None
            or _old_home(policy, snapshot) is not None)


def _old_carry(policy, snapshot):
    if snapshot.player.class_id == PLAYER_CLASS_BERSERKER or not _old_reliable(snapshot):
        return 0
    owned = sum(policy._stack_charges(item)
                for item in (*snapshot.inventory, *destruction_use.staff_home_items(policy, snapshot))
                if policy._is_destruction_staff(item) and item.known and item.charges > 0)
    return min(DESTRUCTION_USES_PER_STEP, owned)


def _old_optimizer_first(policy, snapshot):
    """(the without-gear answer, the staff-owned answer) of _optimizer_destruction_means."""
    if (me_capability.replacing_charges(policy, snapshot, destruction_use.STAFF) > 0
            or any(policy._is_destruction_scroll(item) and item.count > 0
                   for item in snapshot.inventory)):
        return True, None
    return False, not (snapshot.player.class_id == PLAYER_CLASS_BERSERKER
                       or not _old_owns(policy, snapshot))


def _item(slot, tval, sval, count, charges=0, known=True):
    return InventoryItem(slot=slot, name="*Destruction*", count=count, tval=tval, sval=sval,
                         aware=True, known=known, charges=charges)


PACKS = {
    "none": (),
    "scroll": (_item("x", TVAL_SCROLL, SV_SCROLL_STAR_DESTRUCTION, 2),),
    "staff": (_item("y", TVAL_STAFF, SV_STAFF_DESTRUCTION, 1, charges=4),),
    "staves": (_item("y", TVAL_STAFF, SV_STAFF_DESTRUCTION, 2, charges=6),),
    "spent": (_item("y", TVAL_STAFF, SV_STAFF_DESTRUCTION, 1, charges=0),),
    "untried": (_item("y", TVAL_STAFF, SV_STAFF_DESTRUCTION, 1, charges=3, known=False),),
    "both": (_item("x", TVAL_SCROLL, SV_SCROLL_STAR_DESTRUCTION, 1),
             _item("y", TVAL_STAFF, SV_STAFF_DESTRUCTION, 1, charges=2)),
}


class DestructionMeansFactTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory(prefix="destruction-means-")
        cls.policy, _journal, steps = load(FIXTURE, Path(cls.scratch.name))
        board = None
        for recorded, supply in steps[:7]:
            board = supply()
            cls.policy.choose_key(board)
            cls.policy.confirm_key_posted(recorded["key"])
        cls.board = board

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def variant(self, pack, skill, stunned, class_id, in_town):
        inventory = tuple(item for item in self.board.inventory
                          if not destruction_means.is_item(item)) + PACKS[pack]
        player = replace(self.board.player, device_skill=skill, class_id=class_id,
                         stunned=stunned, stun_rank=2 if stunned else None)
        return replace(self.board, inventory=inventory, player=player, town_flag=in_town)

    def test_the_board_is_the_recorded_warrior_with_staves_at_home(self):
        self.assertTrue(self.board.in_town)
        self.assertEqual(sum(item.count for item in destruction_use.staff_home_items(self.policy, self.board)), 12)
        self.assertEqual(self.board.player.device_skill, 32)

    def test_every_reader_answers_as_before(self):
        cases = itertools.product(PACKS, (32, 64, 120), (False, True),
                                  (self.board.player.class_id, PLAYER_CLASS_BERSERKER),
                                  (True, False), (0, 5))
        policy = self.policy
        for pack, skill, stunned, class_id, in_town, absorbed in cases:
            board = self.variant(pack, skill, stunned, class_id, in_town)
            with self.subTest(pack=pack, skill=skill, stunned=stunned, class_id=class_id,
                              in_town=in_town, absorbed=absorbed), \
                    mock.patch.object(me_capability, "replacing_charges", return_value=absorbed):
                self.assertEqual(destruction_use.holds_means(policy, board),
                                 _old_holds_means(policy, board))
                self.assertEqual(policy._total_destruction_uses(board), _old_total_uses(policy, board))
                self.assertEqual(policy._has_destruction_method(board),
                                 _old_total_uses(policy, board) > 0)
                self.assertEqual(destruction_use.owns_charged_staff(policy, board),
                                 _old_owns(policy, board))
                self.assertEqual(destruction_use.staff_carry_uses(policy, board),
                                 _old_carry(policy, board))
                means = destruction_means.Means(policy, board)
                without_gear, staff_owned = _old_optimizer_first(policy, board)
                self.assertEqual(means.optimizer_without_gear(), without_gear)
                if not without_gear:
                    self.assertEqual(means.optimizer_staff_owned(), staff_owned)
                self.assertEqual(destruction_use._reliable_carried_staff(policy, board),
                                 _old_charged(policy, board.inventory) if _old_reliable(board) else None)

    def test_disagreement_is_recorded_and_decides_nothing(self):
        # The recorded board: the Home staves are owned (owns=1) but unreliable at skill 32.
        answers = dict(destruction_means.answers(self.policy, self.board))
        self.assertEqual(answers, {"holds": False, "departure": False, "owns": True, "carry": False,
                                   "optimizer": False, "in-hand": False})
        before = dict(vars(self.policy))
        cross_rules.begin(self.policy)
        cross_rules.end(self.policy, self.board, "5")
        self.assertIn("cross-rule:destruction-means:disagree:"
                      "holds=0/departure=0/owns=1/carry=0/optimizer=0/in-hand=0",
                      cross_rules.report(self.policy))
        self.assertEqual(set(vars(self.policy)), set(before))

    def test_agreement_records_nothing(self):
        board = self.variant("none", 32, False, self.board.player.class_id, False)
        cross_rules.begin(self.policy)
        cross_rules.end(self.policy, board, "5")
        self.assertFalse([row for row in cross_rules.report(self.policy) or ()
                          if row.startswith("cross-rule:destruction-means")])


class DestructionMeansLintTest(unittest.TestCase):
    def test_the_source_has_no_read_off_the_list(self):
        self.assertEqual(destruction_means_lint.findings(), [])

    def test_a_new_read_of_the_kind_fails(self):
        with TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "new_reader.py").write_text(
                "def has_means(policy, snapshot):\n"
                "    return any(policy._is_destruction_staff(i) for i in snapshot.inventory)\n",
                encoding="utf-8")
            (root / "destruction_means.py").write_text(
                "SV_STAFF_DESTRUCTION = 29\nX = SV_STAFF_DESTRUCTION\n", encoding="utf-8")
            sites = destruction_means_lint.sites(root)
        self.assertEqual(sites, [("new_reader", "has_means", 2)])


if __name__ == "__main__":
    unittest.main()
