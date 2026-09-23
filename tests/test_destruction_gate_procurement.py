"""Recorded pins: the 50F+ *Destruction* gate owns a procurement requirement.

Live stop 2026-09-23 18:22/18:23 (protocol 3, the board retained in
``tests/fixtures/unsafe-recall-fallback-20260923.jsonl.gz``): the bot refused
Angband 50 for ``missing-destruction`` while holding 16,288 gold and an EMPTY
``procurement_requirements``.  The gate had no procurement owner at all: no
requirement published it, no purchase pursued it, nothing reserved a carried
copy.  This module pins the owner the user decided on 2026-09-23:

1. 「1 保留の件もいま判断する」 / option 1 「買えるなら買って潜る」 - the
   *Destruction* method joins the departure procurement list; buy it when a
   town store stocks it and the money suffices (respecting the reserve the
   other required supplies hold), otherwise divert to a shallower safe band
   exactly as de62227 does.
2. 「50Fで5回、60Fで10回、70Fで15回とする」 - the required amount scales with
   the target depth, counting the staff's remaining charges plus the number of
   scrolls together (the Identify staff's 20-charge rule).  Beyond 70F the same
   step continues, +5 per 10 levels (80F -> 20).  Below 50F: no requirement.
3. 「3 加速+25は装備加速の話なのでスピードの薬とは別」 - the 81F speed+25 gate
   is an EQUIPMENT speed condition; Potions of Speed do not satisfy it and are
   not procured for it here.
4. 「帰還先の到着階だけ（推奨）」 - the required amount is keyed on the recall
   ARRIVAL DEPTH of the current objective alone.  Going to 50F means 5 uses
   and 60F means 10; carrying one use must not raise the requirement because
   the reachable band widened to the 50-80 rung.
5. 「*破壊*を使用するロジックを実装するまでは実際に50F以降に潜ることを禁止
   する」 - until the bot can actually USE a *Destruction* method in play,
   50F+ is forbidden outright; the deepest permitted arrival or descent is
   49F no matter how many uses are carried.  The ban lives in one named
   condition, ``DESTRUCTION_USE_IMPLEMENTED``, whose entire surface is the two
   functions beside it: ``destruction_dive_permitted`` (the gate refuses the
   arrival) and ``permitted_dive_depth`` (the INTENT is clamped to 49F).

   Refusing the arrival alone was not enough, and the live bot proved it.
   Measured 2026-09-23 22:49, one minute after a resume on main c8d2f10
   (incident 20260923-224927-town-blocked-owner-retired): the requirement,
   keyed on the objective's unclamped arrival depth of 50, still published
   ``{"item": "*Destruction* uses", "current": 0, "target": 5, "missing": 5}``
   -- the ONLY unmet requirement on that board -- so the town walked eight
   decisions to a shop for a ware no fixed shelf can stock, left on
   ``observed-page-nothing-wanted``, wandered three times and retired on
   ``town:blocked:owner-retired``.  Clamping the intent makes the whole owner
   DORMANT, which is what the ban class below pins.  The owner is kept, never
   deleted: every pin describing it runs with the constant flipped, which is
   the state the follow-up round ships.

Substrate: the recorded board above, which is the stop itself.  Depth variants
are that same board with the objective's recall arrival depth replaced, because
the arrival depth is what the recorded stop refused.

Walls, each declared:
- the policy is fresh, not the live process's policy (unavailable).  Home
  history/disposal files live in a temporary directory;
- DECLARED WALL: the objective is Angband.  The recorded reason names
  ``destination-50``, which only the Angband branch of ``_town_departure_key``
  can produce, and the recorded ``dungeon_recall_depths`` gives Angband depth
  50; a fresh policy has not yet selected that objective, so the tests set
  ``_target_dungeon_id`` (identically to
  ``test_unsafe_recall_fallback_recorded``);
- DECLARED WALL: the protocol-3 ~f skill values are the live ones (4000
  two-weapon, 4002 shield, read at CL33 on the recorded 18:23 board).  A fresh
  policy would spend its first decision requesting them.  No pin below depends
  on either value;
- DECLARED WALL: the shelves in the purchase pins are constructed.  Neither
  *Destruction* ware appears in the game's fixed articles-on-sale table (see
  ``item_identity_verification`` in the fix event), so no recorded town page
  can carry one; the pins therefore state the shelf and exercise the selector.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import copy
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import _consume_response_sequence
from hengbot.model import (
    DUNGEON_ANGBAND,
    STORE_ALCHEMIST,
    STORE_BLACK,
    SV_POTION_SPEED,
    SV_SCROLL_STAR_DESTRUCTION,
    SV_STAFF_DESTRUCTION,
    StoreItem,
    StoreState,
    TVAL_POTION,
    TVAL_SCROLL,
    TVAL_STAFF,
)
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import (
    DESTRUCTION_GATE_DEPTH,
    DESTRUCTION_GATE_LABEL,
    DESTRUCTION_USE_IMPLEMENTED,
    SPEED_GATE_DEPTH,
    SPEED_GATE_LABEL,
    WAIT_KEY,
    required_depth_gates,
    required_destruction_uses,
)

from test_esp_threat_rest_recorded import EDIT, _policy
from test_unsafe_recall_fallback_recorded import (
    ANGBAND_ARRIVAL_DEPTH,
    BOUNDARIES_SHA256,
    FIXTURE,
    FIXTURE_SHA256,
    SKILL_EXP,
)


REQUIREMENT = "*Destruction* uses"


def _scroll(letter="a", *, price=750, count=1):
    return StoreItem(
        letter=letter,
        name="*Destruction*",
        count=count,
        tval=TVAL_SCROLL,
        sval=SV_SCROLL_STAR_DESTRUCTION,
        price=price,
    )


def _staff(letter="b", *, price=7500, charges=5):
    return StoreItem(
        letter=letter,
        name="*Destruction*",
        count=1,
        tval=TVAL_STAFF,
        sval=SV_STAFF_DESTRUCTION,
        price=price,
        charges=charges,
        pval=charges,
    )


class _RecordedDestructionBoard:
    """The recorded 2026-09-23 18:23 board, loaded once for both classes."""

    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        boundaries_path = FIXTURE.with_suffix(".boundaries.json")
        assert hashlib.sha256(boundaries_path.read_bytes()).hexdigest() == (
            BOUNDARIES_SHA256
        )
        cls.boundaries = json.loads(
            boundaries_path.read_text(encoding="utf-8")
        )
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.lines = list(stream)
        assert len(cls.lines) == cls.boundaries["input_rows"]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.policy = _policy(self.directory, self.monrace)
        _decoded, snapshots = _consume_response_sequence(
            self.lines, self.policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl",
        )
        self.board = snapshots[-1]
        # DECLARED WALLS (see the module docstring).
        self.policy._target_dungeon_id = DUNGEON_ANGBAND
        self.policy._skill_exp_cache = (
            *SKILL_EXP,
            self.board.player.level,
            self.policy._town_visit_epoch,
        )

    def _independent(self):
        """Deep copy whose cached NeedSpec closures are rebuilt on the copy."""
        clone = copy.deepcopy(self.policy)
        clone._town_need_specs = None
        return clone

    @staticmethod
    def _at_depth(board, depth):
        """The recorded board with the objective's arrival depth replaced."""
        return replace(
            board,
            dungeon_recall_depths={
                **board.dungeon_recall_depths, DUNGEON_ANGBAND: depth
            },
        )

    def _requirement(self, policy, board):
        return next(
            (
                entry
                for entry in policy.procurement_requirements(board)
                if entry["item"] == REQUIREMENT
            ),
            None,
        )

    def _carrying(self, board, *items):
        return replace(board, inventory=[*board.inventory, *items])

    def _destruction_stack(self, board, *, count, charges=0, staff=False):
        """A carried *Destruction* stack built from a recorded pack item."""
        carried = board.inventory[0]
        return replace(
            carried,
            slot="z",
            name="*Destruction*",
            tval=TVAL_STAFF if staff else TVAL_SCROLL,
            sval=SV_STAFF_DESTRUCTION if staff else SV_SCROLL_STAR_DESTRUCTION,
            count=count,
            charges=charges,
            aware=True,
            known=True,
            fully_known=True,
            fuel=0,
            is_equipment=False,
        )

    def _fully_stocked(self, board, uses=20):
        """The same board carrying more uses than any depth could require."""
        return self._carrying(
            board, self._destruction_stack(board, count=uses)
        )


class DestructionGateProcurementTest(
    _RecordedDestructionBoard, unittest.TestCase
):
    """The procurement owner's own behaviour, pinned with the 50F+ ban LIFTED.

    The ban (decision 5) clamps the intended dive depth to 49F, which makes
    this whole owner dormant -- that dormancy is what
    ``DestructionFiftyFloorBanTest`` below pins, with the flag exactly as
    shipped.  These pins describe what the owner does the moment the constant
    is flipped, so the follow-up round inherits a green, meaningful spec
    instead of a deleted one.
    """

    def setUp(self):
        flip = patch(
            "hengbot.policy_constants.DESTRUCTION_USE_IMPLEMENTED", True
        )
        flip.start()
        self.addCleanup(flip.stop)
        super().setUp()

    # ---- D1 -------------------------------------------------------------

    def test_d1_target_50f_with_nothing_carried_requires_five_uses(self):
        policy = self._independent()
        board = self.board

        # The recorded stop: the gate is missing and nothing is carried.
        self.assertEqual(
            self.boundaries["recorded"][-2][1],
            "town:blocked:depth-gate:destination-50:missing-destruction",
        )
        self.assertEqual(self.boundaries["recorded_procurement"], [])
        self.assertEqual(
            policy._dungeon_entry_depth(board, DUNGEON_ANGBAND, via_recall=True),
            ANGBAND_ARRIVAL_DEPTH,
        )
        self.assertEqual(policy._total_destruction_uses(board), 0)

        # REVERT-PROOF: the *achievable* band is capped below the gate while no
        # method is carried, so a requirement keyed on `_planned_depth` alone
        # can never fire.  The intent is the objective's arrival depth.
        self.assertLess(policy._planned_depth(), DESTRUCTION_GATE_DEPTH)
        self.assertEqual(
            policy._intended_dive_depth(board), ANGBAND_ARRIVAL_DEPTH
        )

        self.assertEqual(
            self._requirement(policy, board),
            {
                "item": REQUIREMENT,
                "current": 0,
                "target": 5,
                "missing": 5,
            },
        )

    def test_d1_the_purchase_is_attempted_on_a_stocking_shelf(self):
        policy = self._independent()
        board = self.board
        scroll = _scroll(count=8)
        shelf = replace(
            board, store=StoreState(STORE_BLACK, [scroll]), town_flag=True
        )

        self.assertGreater(shelf.player.gold, 10000)
        self.assertEqual(policy._destruction_purchase(shelf), scroll)
        self.assertEqual(policy._next_purchase(shelf), scroll)
        # The shared rung authority owns the provenance of that selection.
        self.assertIn(
            "mandatory:destruction",
            {
                match.rung_id
                for match in policy._matching_live_purchase_rungs(shelf, scroll)
            },
        )
        # Uses, not stacks: the shortage is five uses, so five scrolls are
        # taken off an eight-deep shelf, not the whole stack and not one.
        self.assertEqual(policy._purchase_quantity(shelf, scroll), 5)

    def test_d1_a_staff_covers_its_charges_in_one_purchase(self):
        policy = self._independent()
        staff = _staff(charges=5)
        shelf = replace(
            self.board,
            store=StoreState(STORE_BLACK, [staff]),
            town_flag=True,
        )

        self.assertEqual(policy._destruction_purchase(shelf), staff)
        self.assertEqual(policy._purchase_quantity(shelf, staff), 1)

    def test_d1_the_other_required_supplies_keep_their_reserve(self):
        policy = self._independent()
        reserve = policy._required_departure_supply_reserve(self.board)
        self.assertIsNotNone(reserve)
        # A ware that would eat into that reserve is refused; the same ware is
        # bought once the purse clears it.
        gold = reserve + 100
        dear = _scroll(price=gold - reserve + 1)
        cheap = _scroll(price=gold - reserve)
        poor = replace(self.board, player=replace(self.board.player, gold=gold))

        self.assertIsNone(
            policy._destruction_purchase(
                replace(poor, store=StoreState(STORE_BLACK, [dear]))
            )
        )
        self.assertEqual(
            policy._destruction_purchase(
                replace(poor, store=StoreState(STORE_BLACK, [cheap]))
            ),
            cheap,
        )

    def test_d1_it_is_not_one_of_the_black_market_optional_picks(self):
        policy = self._independent()
        scroll = _scroll()
        shelf = replace(
            self.board,
            store=StoreState(STORE_BLACK, [scroll]),
            town_flag=True,
        )

        # The optional owner (speed/healing/stone-to-mud) does not claim it.
        self.assertIsNone(policy._black_market_optional_purchase(shelf))
        self.assertEqual(policy._next_purchase(shelf), scroll)

    # ---- D2 -------------------------------------------------------------

    def test_d2_staff_charges_and_scrolls_count_together(self):
        policy = self._independent()
        base = self._at_depth(self.board, 60)
        carried = self.board.inventory[0]

        nine = self._carrying(
            base,
            replace(
                carried,
                slot="y",
                name="*Destruction*",
                tval=TVAL_STAFF,
                sval=SV_STAFF_DESTRUCTION,
                count=1,
                charges=7,
                aware=True,
                known=True,
                fuel=0,
            ),
            replace(
                carried,
                slot="z",
                name="*Destruction*",
                tval=TVAL_SCROLL,
                sval=SV_SCROLL_STAR_DESTRUCTION,
                count=2,
                charges=0,
                aware=True,
                known=True,
                fuel=0,
            ),
        )

        self.assertEqual(policy._total_destruction_uses(nine), 9)
        self.assertEqual(
            self._requirement(policy, nine),
            {
                "item": REQUIREMENT,
                "current": 9,
                "target": 10,
                "missing": 1,
            },
        )
        self.assertEqual(policy._missing_destruction_uses(nine), 1)

        ten = self._carrying(
            base,
            replace(
                carried,
                slot="y",
                name="*Destruction*",
                tval=TVAL_STAFF,
                sval=SV_STAFF_DESTRUCTION,
                count=1,
                charges=8,
                aware=True,
                known=True,
                fuel=0,
            ),
            replace(
                carried,
                slot="z",
                name="*Destruction*",
                tval=TVAL_SCROLL,
                sval=SV_SCROLL_STAR_DESTRUCTION,
                count=2,
                charges=0,
                aware=True,
                known=True,
                fuel=0,
            ),
        )
        self.assertEqual(policy._total_destruction_uses(ten), 10)
        self.assertIsNone(self._requirement(policy, ten))
        self.assertEqual(policy._missing_destruction_uses(ten), 0)
        self.assertIsNone(
            policy._destruction_purchase(
                replace(ten, store=StoreState(STORE_BLACK, [_scroll()]))
            )
        )

    # ---- D3 -------------------------------------------------------------

    def test_d3_the_requirement_scales_with_the_target_depth(self):
        policy = self._independent()

        # REVERT-PROOF: the whole user table, read through the live requirement.
        expected = {49: None, 50: 5, 59: 5, 60: 10, 70: 15, 79: 15, 80: 20}
        for depth, target in expected.items():
            with self.subTest(depth=depth):
                board = self._at_depth(self.board, depth)
                self.assertEqual(policy._intended_dive_depth(board), depth)
                self.assertEqual(required_destruction_uses(depth), target or 0)
                requirement = self._requirement(policy, board)
                if target is None:
                    self.assertIsNone(requirement)
                    self.assertEqual(
                        policy._missing_destruction_uses(board), 0
                    )
                else:
                    self.assertEqual(requirement["target"], target)

    def _one_carried_use(self, board):
        carried = board.inventory[0]
        return self._carrying(
            board,
            replace(
                carried,
                slot="z",
                name="*Destruction*",
                tval=TVAL_SCROLL,
                sval=SV_SCROLL_STAR_DESTRUCTION,
                count=1,
                charges=0,
                aware=True,
                known=True,
                fully_known=True,
                fuel=0,
                is_equipment=False,
            ),
        )

    def test_d3_carrying_one_use_does_not_widen_the_requirement(self):
        """User 2026-09-23 「帰還先の到着階だけ（推奨）」.

        ``divable_depth`` hands a *Destruction* carrier the whole 50-80 rung,
        so the optimizer's next pass publishes band 80.  Keyed on the arrival
        depth alone, a 50F errand still needs 5; keyed on the deeper of band
        and arrival it would jump to 20 the moment the first scroll was bought.
        """
        policy = self._independent()
        one = self._one_carried_use(
            self._at_depth(self.board, ANGBAND_ARRIVAL_DEPTH)
        )
        # DECLARED WALL: the band a carrier is given.  A fresh policy has not
        # run the optimizer on this board; the live one would publish 80 here
        # (divable_depth's 50 rung maps to 80 once has_destruction is true).
        # The widened band is the premise the keying must ignore, never the
        # subject: every assertion below is about the arrival depth.
        policy._equipment_optimization_last_depth = 80

        self.assertEqual(policy._planned_depth(), 80)
        self.assertEqual(policy._total_destruction_uses(one), 1)

        # REVERT-PROOF: the arrival depth alone decides.
        self.assertEqual(
            policy._intended_dive_depth(one), ANGBAND_ARRIVAL_DEPTH
        )
        self.assertEqual(
            self._requirement(policy, one),
            {
                "item": REQUIREMENT,
                "current": 1,
                "target": 5,
                "missing": 4,
            },
        )
        self.assertEqual(policy._missing_destruction_uses(one), 4)

    def test_d3_a_deeper_arrival_raises_it_even_with_a_shallow_band(self):
        """The converse: only the arrival depth moves the figure."""
        policy = self._independent()
        deep = self._one_carried_use(self._at_depth(self.board, 60))

        self.assertLess(policy._planned_depth(), DESTRUCTION_GATE_DEPTH)
        self.assertEqual(policy._intended_dive_depth(deep), 60)
        self.assertEqual(self._requirement(policy, deep)["target"], 10)

    def test_d3_shallower_than_the_gate_has_no_requirement_at_all(self):
        policy = self._independent()
        board = self._at_depth(self.board, DESTRUCTION_GATE_DEPTH - 1)

        self.assertNotIn(
            DESTRUCTION_GATE_LABEL,
            required_depth_gates(DESTRUCTION_GATE_DEPTH - 1),
        )
        self.assertEqual(policy._required_destruction_uses(board), 0)
        self.assertIsNone(self._requirement(policy, board))
        self.assertIsNone(
            policy._destruction_purchase(
                replace(board, store=StoreState(STORE_BLACK, [_scroll()]))
            )
        )

    # ---- D4 -------------------------------------------------------------

    def test_d4_no_stock_and_no_home_copy_still_diverts_instead_of_stopping(self):
        policy = self._independent()
        board = self.board

        # The requirement is live and unmet, and nothing in town supplies it.
        self.assertEqual(self._requirement(policy, board)["missing"], 5)
        self.assertIsNone(
            policy._destruction_purchase(
                replace(board, store=StoreState(STORE_BLACK, []))
            )
        )

        key = policy._town_special_key(board)

        self.assertEqual(
            (key, policy.last_reason), (WAIT_KEY, "town:unsafe-recall-fallback")
        )
        self.assertIsNone(policy._town_blocked_reason)
        self.assertNotEqual(policy._target_dungeon_id, DUNGEON_ANGBAND)
        landing = board.dungeon_recall_depths[policy._target_dungeon_id]
        self.assertLess(landing, ANGBAND_ARRIVAL_DEPTH)
        # Diverted to a shallower safe band, the requirement is gone with it.
        self.assertIsNone(self._requirement(policy, board))

    # ---- D5 -------------------------------------------------------------

    def _with_stock(self, board):
        carried = board.inventory[0]
        return self._carrying(
            board,
            replace(
                carried,
                slot="z",
                name="*Destruction*",
                tval=TVAL_SCROLL,
                sval=SV_SCROLL_STAR_DESTRUCTION,
                count=3,
                charges=0,
                aware=True,
                known=True,
                fully_known=True,
                fuel=0,
                is_equipment=False,
            ),
        )

    def test_d5_carried_destruction_is_never_surplus_while_the_target_is_deep(self):
        policy = self._independent()
        board = self._with_stock(self.board)
        held = board.inventory[-1]

        self.assertEqual(policy._retention_surplus(board, held), 0)
        self.assertFalse(policy._entire_stack_is_surplus(board, held))
        self.assertTrue(policy._item_is_procurement_protected(board, held))
        self.assertEqual(
            policy._retention_reservation_detail(board, held),
            (held.count, "destruction-gate"),
        )
        self.assertIsNot(policy._overflow_disposal_item(board), held)
        self.assertIsNot(policy._find_disposable_item(board), held)

    def test_d5_a_shallow_target_leaves_the_reservation_to_other_owners(self):
        policy = self._independent()
        board = self._with_stock(
            self._at_depth(self.board, DESTRUCTION_GATE_DEPTH - 1)
        )
        held = board.inventory[-1]

        self.assertEqual(policy._required_destruction_uses(board), 0)
        self.assertNotEqual(
            policy._retention_reservation_detail(board, held)[1],
            "destruction-gate",
        )
        # NON-VACUITY for the deep-target pin above: with no requirement the
        # same stack is ordinary surplus, so the reservation there is the
        # thing being asserted, not an unconditional refusal.
        self.assertEqual(policy._retention_surplus(board, held), held.count)
        self.assertTrue(policy._entire_stack_is_surplus(board, held))

    # ---- D6 -------------------------------------------------------------

    def test_d6_potions_of_speed_do_not_satisfy_the_81f_speed_gate(self):
        policy = self._independent()
        carried = self.board.inventory[0]
        board = self._at_depth(
            self._carrying(
                self.board,
                replace(
                    carried,
                    slot="z",
                    name="Speed",
                    tval=TVAL_POTION,
                    sval=SV_POTION_SPEED,
                    count=9,
                    charges=0,
                    aware=True,
                    known=True,
                    fuel=0,
                ),
            ),
            SPEED_GATE_DEPTH,
        )

        self.assertIn(SPEED_GATE_LABEL, required_depth_gates(SPEED_GATE_DEPTH))
        self.assertLess(board.player.speed, 135)
        self.assertIn(
            SPEED_GATE_LABEL,
            policy._missing_required_abilities(board, SPEED_GATE_DEPTH),
        )
        self.assertFalse(
            policy._destination_depth_allowed(board, SPEED_GATE_DEPTH)
        )
        # Nor do they count as a *Destruction* use, or get procured for it.
        self.assertEqual(policy._total_destruction_uses(board), 0)
        self.assertIsNone(
            policy._destruction_purchase(
                replace(
                    board,
                    store=StoreState(
                        STORE_BLACK,
                        [
                            StoreItem(
                                letter="a",
                                name="Speed",
                                count=1,
                                tval=TVAL_POTION,
                                sval=SV_POTION_SPEED,
                                price=500,
                            )
                        ],
                    ),
                )
            )
        )



class DestructionFiftyFloorBanTest(
    _RecordedDestructionBoard, unittest.TestCase
):
    """The 50F+ ban, pinned with ``DESTRUCTION_USE_IMPLEMENTED`` AS SHIPPED.

    User 2026-09-23
    「*破壊*を使用するロジックを実装するまでは実際に50F以降に潜ることを禁止
    する」.  These pins are the live behaviour today; the procurement class
    above describes what returns when the constant is flipped.
    """

    def test_d7_fifty_f_is_refused_however_many_uses_are_carried(self):
        policy = self._independent()
        stocked = self._fully_stocked(self.board)

        self.assertFalse(DESTRUCTION_USE_IMPLEMENTED)
        self.assertEqual(policy._total_destruction_uses(stocked), 20)
        self.assertEqual(policy._missing_destruction_uses(stocked), 0)

        # Possession is not the missing piece: the use-logic is.
        self.assertEqual(
            sorted(
                policy._missing_required_abilities(
                    stocked, ANGBAND_ARRIVAL_DEPTH
                )
            ),
            [DESTRUCTION_GATE_LABEL],
        )
        self.assertFalse(
            policy._destination_depth_allowed(stocked, ANGBAND_ARRIVAL_DEPTH)
        )
        self.assertEqual(
            f"town:blocked:{policy.last_reason}",
            "town:blocked:depth-gate:destination-50:missing-destruction",
        )
        self.assertFalse(
            policy._recall_destination_safe(stocked, DUNGEON_ANGBAND)
        )

    def test_d7_the_deepest_permitted_arrival_and_descent_is_49f(self):
        policy = self._independent()
        stocked = self._fully_stocked(self.board)

        self.assertEqual(
            policy._missing_required_abilities(
                stocked, DESTRUCTION_GATE_DEPTH - 1
            ),
            frozenset(),
        )
        self.assertTrue(
            policy._destination_depth_allowed(
                stocked, DESTRUCTION_GATE_DEPTH - 1
            )
        )
        # The first banned floor, and everything below it.
        for depth in (
            DESTRUCTION_GATE_DEPTH, DESTRUCTION_GATE_DEPTH + 1, 60, 80,
        ):
            with self.subTest(depth=depth):
                self.assertIn(
                    DESTRUCTION_GATE_LABEL,
                    policy._missing_required_abilities(stocked, depth),
                )
                self.assertFalse(
                    policy._destination_depth_allowed(stocked, depth)
                )

    def test_d7_the_objective_diverts_to_a_shallower_band_and_never_stops(self):
        policy = self._independent()
        stocked = self._fully_stocked(self.board)

        key = policy._town_special_key(stocked)

        self.assertEqual(
            (key, policy.last_reason), (WAIT_KEY, "town:unsafe-recall-fallback")
        )
        self.assertIsNone(policy._town_blocked_reason)
        self.assertNotEqual(policy._target_dungeon_id, DUNGEON_ANGBAND)
        landing = stocked.dungeon_recall_depths[policy._target_dungeon_id]
        self.assertLess(landing, DESTRUCTION_GATE_DEPTH)

    def test_d7_flipping_the_named_condition_restores_the_50f_behaviour(self):
        """The follow-up round's green target: one flag, nothing else."""
        stocked = self._fully_stocked(self.board)

        with patch(
            "hengbot.policy_constants.DESTRUCTION_USE_IMPLEMENTED", True
        ):
            policy = self._independent()
            self.assertEqual(
                policy._missing_required_abilities(
                    stocked, ANGBAND_ARRIVAL_DEPTH
                ),
                frozenset(),
            )
            self.assertTrue(
                policy._destination_depth_allowed(
                    stocked, ANGBAND_ARRIVAL_DEPTH
                )
            )
            self.assertTrue(
                policy._recall_destination_safe(stocked, DUNGEON_ANGBAND)
            )
            self.assertIsNone(policy._town_special_key(stocked))
            self.assertEqual(policy._target_dungeon_id, DUNGEON_ANGBAND)
            # With the depth reachable again, an empty pack is short 5 uses:
            # the procurement owner is dormant, not deleted.
            empty = self._independent()
            self.assertEqual(
                self._requirement(empty, self.board)["missing"], 5
            )

    # ---- D8: the requirement is dormant while the ban holds ---------------

    def test_d8_the_requirement_is_empty_while_the_ban_holds(self):
        """Live stop 2026-09-23 22:49 (see the module docstring).

        Refusing only the arrival left the intent at 50, so the requirement
        still published 5 missing uses for a depth the gate would refuse.
        """
        policy = self._independent()
        board = self.board

        # The objective still arrives at 50: the ban refuses it, it does not
        # change it.  That is exactly why the INTENT has to be clamped too.
        self.assertEqual(
            policy._dungeon_entry_depth(board, DUNGEON_ANGBAND, via_recall=True),
            ANGBAND_ARRIVAL_DEPTH,
        )

        # REVERT-PROOF: unclamped, this is 50 and the requirement is 5/5.
        self.assertEqual(
            policy._intended_dive_depth(board), DESTRUCTION_GATE_DEPTH - 1
        )
        self.assertEqual(policy._required_destruction_uses(board), 0)
        self.assertEqual(policy._missing_destruction_uses(board), 0)
        self.assertIsNone(self._requirement(policy, board))
        self.assertEqual(
            [
                entry
                for entry in policy.procurement_requirements(board)
                if entry["item"] == REQUIREMENT
            ],
            [],
        )

    def test_d8_no_shop_errand_is_generated_for_the_dormant_requirement(self):
        policy = self._independent()
        board = self.board

        # Nothing to buy anywhere, on a stocking shelf or an ordinary one.
        for store_type, wares in (
            (STORE_BLACK, [_scroll(), _staff()]),
            (STORE_ALCHEMIST, []),
        ):
            with self.subTest(store=store_type):
                page = replace(
                    board,
                    store=StoreState(store_type, wares),
                    town_flag=True,
                )
                self.assertIsNone(policy._destruction_purchase(page))
                self.assertEqual(
                    policy._matching_live_purchase_rungs(page, _scroll()), ()
                )

        # And the town errand registry raises no destruction claim.
        self.assertTrue(policy._town_claims_active(board) in (True, False))
        self.assertNotIn(
            "destruction", getattr(policy, "_town_claim_categories", ())
        )

    def test_d8_a_carried_copy_is_ordinary_surplus_while_dormant(self):
        """The retention reservation sleeps with the rest of the owner."""
        policy = self._independent()
        board = self._carrying(
            self.board, self._destruction_stack(self.board, count=3)
        )
        held = board.inventory[-1]

        self.assertNotEqual(
            policy._retention_reservation_detail(board, held)[1],
            "destruction-gate",
        )
        with patch(
            "hengbot.policy_constants.DESTRUCTION_USE_IMPLEMENTED", True
        ):
            restored = self._independent()
            self.assertEqual(
                restored._retention_reservation_detail(board, held),
                (held.count, "destruction-gate"),
            )


if __name__ == "__main__":
    unittest.main()
