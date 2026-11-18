"""The *Destruction* means is one fact (hengbot.destruction_means) and every reader answers by the
depth condition's definition.

Whole-bot maintainability review 2026-11-16 (R1).  Stage 2 gathered the readers' facts (main
a44f4593e7's readings kept); stage 3, owner review section 6 Q1 verbatim 「深さの条件の定義に揃える」:
every reader of "is there a *Destruction* means" answers by destruction_use.holds_means (a staff or
the absorbed power at 80%+ with a charge, in town a Home staff at 80%; a scroll is no means, owner
2026-11-04).  Counts keep their quantity but count only what the definition counts.  The invariant
(destruction_means.violations) is recorded by ``cross-rule:destruction-means:broken``.

Recorded: the n1-a life-525 21:05:39 town-arrival checkpoint (tests/fixtures/n1a-525-departure-1115,
a Lv40 Warrior, device skill 32, twelve charged staves of *Destruction* in the Home), row 6's board
through the public choose_key.

DECLARED CONSTRUCTED:
* ``variant``: row 6's board with the pack, the device skill, the stun, the class and the town flag
  named per case; the absorbed staff's charges (me_capability.replacing_charges) are given per case.
* ``_definition`` and the ``_ref_*`` helpers: the definition (holds_means as main a44f4593e7 wrote
  it, unchanged) and the facts the expected answers are built from.
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


# -- the definition (main a44f4593e7's holds_means, unchanged) and its facts ------------------

def _ref_reliable(snapshot):
    return destruction_use.staff_success(snapshot.player, 50) >= me_capability.RELIABLE_MIN_SUCCESS


def _ref_charged(policy, items):
    return next((item for item in items if policy._is_destruction_staff(item) and item.known
                 and item.charges > 0), None)


def _ref_home(policy, snapshot):
    return next(iter(destruction_use.staff_home_items(policy, snapshot)), None)


def _ref_absorbed(policy, snapshot):
    return me_capability.replacing_charges(policy, snapshot, destruction_use.STAFF)


def _ref_owned(policy, snapshot):
    """A known charged staff carried or (town) in the Home, the success not asked."""
    return (_ref_charged(policy, snapshot.inventory) is not None
            or _ref_home(policy, snapshot) is not None)


def _definition(policy, snapshot):
    return (_ref_absorbed(policy, snapshot) > 0
            or (_ref_reliable(snapshot) and _ref_charged(policy, snapshot.inventory) is not None)
            or (_ref_reliable(snapshot) and _ref_home(policy, snapshot) is not None))


def _ref_departure_uses(policy, snapshot):
    """The absorbed charges and, when reliable, the carried known staves' charges; no scroll."""
    staves = sum(policy._stack_charges(item) for item in snapshot.inventory
                 if policy._is_destruction_staff(item) and item.known and item.charges > 0)
    return _ref_absorbed(policy, snapshot) + (staves if _ref_reliable(snapshot) else 0)


def _ref_carry(policy, snapshot):
    if snapshot.player.class_id == PLAYER_CLASS_BERSERKER or not _ref_reliable(snapshot):
        return 0
    owned = sum(policy._stack_charges(item)
                for item in (*snapshot.inventory, *destruction_use.staff_home_items(policy, snapshot))
                if policy._is_destruction_staff(item) and item.known and item.charges > 0)
    return min(DESTRUCTION_USES_PER_STEP, owned)


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

    def test_every_reader_answers_by_the_definition(self):
        cases = itertools.product(PACKS, (32, 64, 120), (False, True),
                                  (self.board.player.class_id, PLAYER_CLASS_BERSERKER),
                                  (True, False), (0, 5))
        policy = self.policy
        for pack, skill, stunned, class_id, in_town, absorbed in cases:
            board = self.variant(pack, skill, stunned, class_id, in_town)
            with self.subTest(pack=pack, skill=skill, stunned=stunned, class_id=class_id,
                              in_town=in_town, absorbed=absorbed), \
                    mock.patch.object(me_capability, "replacing_charges", return_value=absorbed):
                definition = _definition(policy, board)
                reliable = _ref_reliable(board)
                self.assertEqual(destruction_use.holds_means(policy, board), definition)
                self.assertEqual(policy._has_destruction_method(board), definition)
                uses = policy._total_destruction_uses(board)
                self.assertEqual(uses, _ref_departure_uses(policy, board))
                self.assertTrue(uses == 0 or definition)
                self.assertEqual(destruction_use.owns_charged_staff(policy, board),
                                 reliable and _ref_owned(policy, board))
                self.assertEqual(destruction_use.staff_carry_uses(policy, board),
                                 _ref_carry(policy, board))
                means = destruction_means.Means(policy, board)
                self.assertEqual(means.staff_owned, _ref_owned(policy, board))
                self.assertEqual(means.optimizer_without_gear(), absorbed > 0)
                self.assertEqual(means.optimizer_staff_owned(),
                                 class_id != PLAYER_CLASS_BERSERKER and _ref_owned(policy, board))
                self.assertEqual(destruction_use._reliable_carried_staff(policy, board),
                                 _ref_charged(policy, board.inventory) if reliable else None)
                for item in PACKS["both"]:
                    self.assertEqual(policy._supplies_destruction(board, item),
                                     policy._is_destruction_staff(item) and reliable)
                self.assertEqual(destruction_means.violations(policy, board), ())

    def test_a_scroll_alone_is_no_means_for_any_reader(self):
        # Stage 2's one replayed disagreement (72 decisions): *Destruction* scrolls only.
        board = self.variant("scroll", 120, False, self.board.player.class_id, False)
        with mock.patch.object(me_capability, "replacing_charges", return_value=0):
            self.assertEqual(dict(destruction_means.answers(self.policy, board)),
                             {name: False for name, _reader, _exact in destruction_means.COMBINATIONS})
            self.assertEqual(self.policy._total_destruction_uses(board), 0)
            self.assertFalse(self.policy._supplies_destruction(board, PACKS["scroll"][0]))

    def test_an_unreliable_home_staff_is_owned_but_no_means(self):
        # The recorded board: twelve Home staves at 32 device skill (below 80%).
        means = destruction_means.Means(self.policy, self.board)
        self.assertTrue(means.staff_owned)  # the gear search still sees the staves
        self.assertFalse(destruction_use.owns_charged_staff(self.policy, self.board))
        answers = dict(destruction_means.answers(self.policy, self.board))
        self.assertFalse(any(answers.values()), answers)
        cross_rules.begin(self.policy)
        cross_rules.end(self.policy, self.board, "5")
        self.assertFalse([row for row in cross_rules.report(self.policy) or ()
                          if row.startswith("cross-rule:destruction-means")])

    def test_a_reliable_home_staff_is_held_in_town_only(self):
        for in_town in (True, False):
            board = self.variant("none", 120, False, self.board.player.class_id, in_town)
            with self.subTest(in_town=in_town), \
                    mock.patch.object(me_capability, "replacing_charges", return_value=0):
                self.assertEqual(destruction_use.holds_means(self.policy, board), in_town)
                self.assertEqual(destruction_use.owns_charged_staff(self.policy, board), in_town)
                # Counted once carried: the departure takes it from the Home first.
                self.assertEqual(self.policy._total_destruction_uses(board), 0)
                # A 50F+ arrival asks it carried (owner 2026-11-18, n1-a life-530).
                self.assertFalse(destruction_means.departure_carried(self.policy, board, 50))
                self.assertTrue(destruction_means.departure_carried(self.policy, board, 49))
                self.assertEqual(destruction_means.violations(self.policy, board), ())

    def test_a_broken_invariant_is_recorded_and_decides_nothing(self):
        before = dict(vars(self.policy))
        with mock.patch.object(destruction_use, "owns_charged_staff", return_value=True):
            self.assertEqual(destruction_means.violations(self.policy, self.board), ("owns",))
            cross_rules.begin(self.policy)
            cross_rules.end(self.policy, self.board, "5")
        self.assertIn("cross-rule:destruction-means:broken:holds=0/departure=0/departure-uses=0/"
                      "owns=1/carry=0/optimizer=0/in-hand=0/carried=0", cross_rules.report(self.policy))
        self.assertEqual(set(vars(self.policy)), set(before))


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
