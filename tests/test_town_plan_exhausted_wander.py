"""Recorded pins: an exhausted town plan must not end in an unbounded wander.

Two stops of the same shape on 2026-09-23, each one minute after a resume
(22:49 and 23:53; both captures are a whole 64-decision bot process).  The bot
is in Morivant (town_id 2), whose map has no dungeon entrance and whose emitted
grids hold none either.  Its plan has one stop, the Alchemist, built for a
``stat-restore`` errand; the observed page wants nothing
(``observed-page-nothing-wanted``), the plan index moves past its only stop and
no town claim is left.

Root cause, measured on these boards: the fundraising plan is ``mine`` with the
kit secured, so ``_town_recall_destination`` refuses every recall destination
in order to make the bot walk in at level one, and
``_town_special_key`` returns None at the ready-fundraising-departure exit to
hand that walk to the generic descent router.  From Morivant the walk has no
goal -- ``_is_descent_target`` accepts a Yeek Cave entrance only from town 0,
and ``_town_map_descent_entrance`` has no entrance in this town's map -- so the
router reported ``no-known-downstairs``, the fully-known town offered no
frontier, and the last-resort ``stuck:wander`` ran three times until the town
arbiter retired ``detectors`` and the driver stopped on
``town:blocked:owner-retired``.

Fix (user decision 2026-09-24, 「採掘の段で、入口の無い町にいる時はどうします
か」 -> 「町0へ戻る（推奨）」): the stranded plan returns to the Outpost through
the cross-town machinery the Morivant *Identify* trip already uses
(``_town_teleport_key``) and walks in from there.  It never reads a Word of
Recall: the mine phase refuses recall destinations to conserve scrolls, and
that intent is unchanged.  The reason keeps the ``town:cross-town`` prefix, so
the trip is owned and bounded by that family's existing budget and retirement
rules.  When the return is itself impossible -- no fare, no reachable Inn, no
legal exit, or this is already town 0 -- the honest stop remains the fallback.

The earlier round's diagnosis (``_departure_supplier_counterfactual`` at the
departure block clearing ``_town_blocked_reason`` and returning None) is
refuted for these boards: that whole block is guarded by
``recall_dest is not None``, the recall destination here is None, and the
counterfactual supplier is None as well.  P0 below asserts both facts.

Fixture: tests/fixtures/town-plan-exhausted-wander-20260923.jsonl.gz, written
by tests/extract_town_plan_exhausted_wander_fixture.py (the provenance file
beside it names all three source files of both captures by sha256, the ring
reading rule and the decision boundaries).

pin_vacuity: the captures hold boards, decision facts and a JSON state dump,
not a restorable policy checkpoint.  Each pin therefore runs the production
producer over the five recorded input boards of the recorded window, with
exactly the recorded pre-decision facts re-attached, in the manner of the
posted-effect-unobserved pins: the capture's own errand plan (rewound to the
index it had before the first frozen decision), its StoreVisit, its Home
catalogue bookkeeping, its fundraising mode and planned run count, and this
visit's purchase/attempt ledgers.  Every pin first asserts the recorded stop it
reproduces, and P1/P2 assert the recorded ``stuck:wander`` decisions and the
recorded retirement stop are gone.  P5 is the same replay with the Inn fare out
of reach, which is the one recorded-board change it makes.

Walls, each on a collaborator that is not under test:
- the Home disposal/history files live in a temporary directory;
- the recorded process's ``~f`` skill list is handed to the public
  ``consume_skill_knowledge`` instead of being re-requested, so the replay does
  not spend a decision on the periodic probe;
- the capture retains no Home catalogue page, so ``_home_knowledge_scan_requested``
  is set to the value the recorded ``~9`` scan of this visit left
  (``_home_scan_source`` in the state dump proves that scan was made and
  answered); without it the replay would re-request the page it cannot restore.

P4 relies on the existing retirement-bound pins, which this change does not
touch: tests/test_town_arbiter.py
``test_equipment_home_equidistant_oscillation_retires_at_stall_budget`` and
``test_nonconverging_store_walk_retires_within_recurrence_budget``.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.policy_fixtures import grid, player

from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.home_disposal import HomeDisposalState
from hengbot.model import (
    DUNGEON_YEEK_CAVE,
    PLAYER_CLASS_WARRIOR,
    Position,
    Snapshot,
    parse_snapshot,
)
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import (
    OUTPOST_TOWN_ID,
    POLICY_FINAL_STOP_REASONS,
    READ_KEY,
    TOWN_TELEPORT_COST,
)
from hengbot.policy_types import StoreVisit, StoreVisitPhase, TownErrandPlan
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies
from hengbot.terrain_knowledge import load_damaging_terrain_ids
from hengbot.town_arbiter import reason_owner_family
from hengbot.town_maps import find_town_map, parse_town_map
from hengbot.wilderness_map import find_wilderness_definition, load_wilderness_map


ROOT = Path(__file__).resolve().parents[1]
GAME_ROOT = Path("C:/hengband")
EDIT = GAME_ROOT / "lib" / "edit"
FIXTURE = (
    ROOT / "tests" / "fixtures" / "town-plan-exhausted-wander-20260923.jsonl.gz"
)
FIXTURE_SHA256 = (
    "5a1083fa3a7aa7a9d84cb9090e64256a8f0426315eec49f3c71924969764be7d"
)
DESTRUCTION_STOP = "20260923-224927-town-blocked-owner-retired"
EMPTY_STOP = "20260923-235359-town-blocked-owner-retired"
WINDOW = (59, 60, 61, 62, 63)
MORIVANT_TOWN_ID = 2
ALCHEMIST = 4
BLOCKED_REASON = "town:blocked:walk-in-entrance-unavailable"
RETURN_REASON = "town:cross-town-walk-in-return"


def _records():
    with gzip.open(FIXTURE, "rb") as stream:
        return [json.loads(line) for line in stream]


class TownPlanExhaustedWanderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        records = _records()
        cls.skill = {
            record["capture"]: record["board"]
            for record in records if record["role"] == "skill-knowledge"
        }
        cls.inputs = {
            (record["capture"], record["decision"]["decision_sequence"]): record
            for record in records if record["role"] == "decision-input"
        }
        cls.state = {
            record["capture"]: record["fields"]
            for record in records if record["role"] == "policy-state"
        }

    # -- helpers ---------------------------------------------------------
    def _decision(self, capture, sequence):
        return self.inputs[(capture, sequence)]["decision"]

    def _board(self, capture, sequence):
        return parse_snapshot(self.inputs[(capture, sequence)]["board"], self.monrace)

    def _fresh_policy(self, directory):
        town_maps = {}
        for town_index in range(1, 6):
            path = find_town_map(town_index, GAME_ROOT)
            if path is not None:
                town_maps[town_index - 1] = parse_town_map(path)
        policy = HengbotPolicy(
            town_map=town_maps.get(0),
            town_maps=town_maps,
            wilderness_map=load_wilderness_map(
                find_wilderness_definition(GAME_ROOT)
            ),
            dungeon_knowledge=load_dungeon_knowledge(
                EDIT / "DungeonDefinitions.jsonc"
            ),
            monrace_knowledge=self.monrace,
            damaging_terrain_ids=load_damaging_terrain_ids(
                EDIT / "TerrainDefinitions.jsonc"
            ),
            quest_knowledge=load_quest_knowledge(
                find_quest_definitions(GAME_ROOT / "bot-client" / "state.jsonl")
            ),
            quest_strategies=load_quest_strategies(ROOT / "strategy" / "quests"),
            home_disposal_state=HomeDisposalState(
                directory / "home-withdraw-history.jsonc",
                directory / "home-disposal-decisions.jsonc",
                directory / "home-disposal-queue.json",
                directory / "events.jsonl",
            ),
            baseitem_costs=load_baseitem_costs(EDIT / "BaseitemDefinitions.jsonc"),
        )
        policy._character_calibration_path = directory / "character-calibration.json"
        return policy

    def _restore(self, policy, capture, *, planned_mining_runs=True):
        """Re-attach the recorded pre-decision facts of the frozen window."""
        fields = self.state[capture]
        decision = self._decision(capture, WINDOW[0])
        plan = fields["_town_errand_plan"]
        # The dump was written after the stop, so its index is already past the
        # only stop.  Rewind to the index the frozen decision was taken with
        # (the recorded town_plan of decision 58); the producer advances it.
        policy._town_errand_plan = TownErrandPlan(
            stops=list(plan["stops"]),
            need_categories={
                int(store): tuple(categories)
                for store, categories in plan["need_categories"].items()
            },
            index=0,
        )
        visit = decision["store_visit"]
        policy._store_visit = StoreVisit(
            owner=visit["owner"],
            purpose=visit["purpose"],
            store_type=visit["store_type"],
            phase=StoreVisitPhase.ENTERING,
            visit_origin=visit["visit_origin"],
            opened_sequence=visit["opened_sequence"],
        )
        policy._shopping_approach_store_type = visit["store_type"]
        policy._home_knowledge_current = fields["_home_knowledge_current"]
        policy._home_knowledge_valid_before = fields["_home_knowledge_valid_before"]
        policy._home_page_size = fields["_home_page_size"]
        policy._home_scan_source = fields["_home_scan_source"]
        policy._home_scan_item_count = fields["_home_scan_item_count"]
        # WALL: this visit's ~9 page is not retained by the capture; the scan
        # was made (_home_scan_source above) and must not be re-requested.
        policy._home_knowledge_scan_requested = True
        policy._home_candidate_waiting = decision["home_candidate_waiting"]
        policy._fundraising_mode = fields["_fundraising_mode"]
        if planned_mining_runs:
            policy._planned_mining_runs = decision["fundraising"]["planned_runs"]
        policy._observed_town_id = fields["_observed_town_id"]
        policy._town_was_in_town = fields["_town_was_in_town"]
        policy._yeek_conquest_processed = fields["_yeek_conquest_processed"]
        policy._town_no_progress_count = fields["_town_no_progress_count"]
        policy._town_wander_streak = fields["_town_wander_streak"]
        policy._town_store_attempted = {
            int(store): turn
            for store, turn in fields["_town_store_attempted"].items()
        }
        policy._town_visit_purchases = {
            tuple(signature) for signature in fields["_town_visit_purchases"]
        }
        policy._town_visit_purchase_quantities = {
            tuple(json.loads(signature.replace("'", '"'))): quantity
            for signature, quantity
            in fields["_town_visit_purchase_quantities"].items()
        }

    def _drive(self, capture, *, planned_mining_runs=True, gold=None):
        """Decide the recorded boards of the window, as the driver would.

        The driver stops instead of deciding again once the policy names a
        declared final stop (cli._policy_final_stop_banner), so the replay
        stops there too.
        """
        boards = [self._board(capture, sequence) for sequence in WINDOW]
        if gold is not None:
            boards = [
                replace(board, player=replace(board.player, gold=gold))
                for board in boards
            ]
        with TemporaryDirectory() as raw_directory:
            policy = self._fresh_policy(Path(raw_directory))
            policy.prime(boards[0])
            policy.consume_skill_knowledge(self.skill[capture])
            self._restore(
                policy, capture, planned_mining_runs=planned_mining_runs
            )
            emitted = []
            for sequence, board in zip(WINDOW, boards):
                policy._decision_sequence = sequence
                key = policy.validate_read_key(board, policy.choose_key(board))
                emitted.append(
                    (str(key) if key is not None else None, policy.last_reason)
                )
                if policy.last_reason in POLICY_FINAL_STOP_REASONS:
                    break
                policy.confirm_key_posted(key)
            return emitted

    # -- the recorded stops ----------------------------------------------
    def test_fixture_freezes_the_two_recorded_stops(self):
        for capture in (DESTRUCTION_STOP, EMPTY_STOP):
            with self.subTest(capture=capture):
                recorded = [
                    (self._decision(capture, sequence)["key"],
                     self._decision(capture, sequence)["reason"])
                    for sequence in WINDOW
                ]
                self.assertEqual(recorded[0][1], "shop:observe-and-leave")
                self.assertEqual(
                    [reason for _key, reason in recorded[1:4]],
                    ["stuck:wander"] * 3,
                )
                self.assertEqual(recorded[4][1], "town:blocked:owner-retired")
                leave = self._decision(capture, 59)
                self.assertEqual(leave["store_type"], ALCHEMIST)
                self.assertEqual(
                    leave["shop_selector"]["rejection_reason"],
                    "observed-page-nothing-wanted",
                )
                self.assertEqual(
                    leave["town_plan"], {
                        "stops": ["Alchemist"], "index": 1,
                        "inserted_this_visit": [], "skipped_latched": [],
                    },
                )
                # The arbiter retires the generic wander owner, then town-plan
                # inherits a board it cannot act on.
                self.assertEqual(
                    self._decision(capture, 62)["arbiter"]["retirement_set"],
                    ["detectors"],
                )
                self.assertEqual(
                    self._decision(capture, 63)["arbiter"]["owner"], "town-plan"
                )
                # The plan's only stop was built for a stat-restore errand.
                self.assertEqual(
                    self.state[capture]["_town_errand_plan"]["need_categories"],
                    {"4": ["stat-restore"]},
                )
                self.assertEqual(
                    self.state[capture]["_fundraising_mode"], "mine"
                )
                self.assertEqual(
                    self._decision(capture, 59)["fundraising"]["kit_secured"], True
                )

    def test_both_stops_are_the_same_shape_in_different_procurement_states(self):
        self.assertEqual(
            [
                row["item"]
                for row in self._decision(
                    DESTRUCTION_STOP, 59
                )["procurement_requirements"]
            ],
            ["*Destruction* uses"],
        )
        self.assertEqual(
            self._decision(EMPTY_STOP, 59)["procurement_requirements"], []
        )

    def test_p0_the_stop_town_has_no_entrance_the_mining_walk_can_use(self):
        """Root cause, and the refutation of the earlier round's diagnosis."""
        for capture in (DESTRUCTION_STOP, EMPTY_STOP):
            with self.subTest(capture=capture):
                board = self._board(capture, 63)
                self.assertEqual(board.town_id, MORIVANT_TOWN_ID)
                self.assertTrue(board.in_town)
                with TemporaryDirectory() as raw_directory:
                    policy = self._fresh_policy(Path(raw_directory))
                    policy.prime(board)
                    policy.consume_skill_knowledge(self.skill[capture])
                    self._restore(policy, capture)
                    known = policy.with_known_skill_exp(board)
                    # No emitted grid of the whole town is a walking route to
                    # the mining target, and this town's map has no entrance.
                    self.assertGreater(len(known.grids), 10_000)
                    self.assertIsNone(policy._town_walk_in_entrance(known))
                    self.assertIsNone(
                        policy._town_map_descent_entrance(known)
                    )
                    # The mining plan refuses every recall destination, so the
                    # whole ``recall_dest is not None`` departure block -- the
                    # earlier round's suspected site -- is skipped, and its
                    # supplier counterfactual is None in any case.
                    destination, _dungeon = policy._town_recall_destination(known)
                    self.assertIsNone(destination)
                    self.assertIsNone(
                        policy._departure_supplier_counterfactual(known)
                    )
                    self.assertFalse(policy._town_claims_active(known))
                    self.assertTrue(
                        policy._fundraising_departure_ready(known)
                    )

    # -- P1 / P2 ---------------------------------------------------------
    def _assert_cross_town_return_replaces_the_wander(self, capture):
        emitted = self._drive(capture)
        reasons = [reason for _key, reason in emitted]
        # The recorded first decision of the window is unchanged.
        self.assertEqual(reasons[0], "shop:observe-and-leave")
        self.assertEqual(emitted[0][0], self._decision(capture, 59)["key"])
        # The three recorded wanders and the recorded retirement stop are gone,
        # and so is the blocked stop: the return to the Outpost is available.
        self.assertNotIn("stuck:wander", reasons)
        self.assertNotIn("town:blocked:owner-retired", reasons)
        self.assertNotIn(BLOCKED_REASON, reasons)
        self.assertEqual(reasons[1:], [RETURN_REASON] * (len(emitted) - 1))
        # The trip is owned and bounded by the existing cross-town family.
        self.assertEqual(reason_owner_family(RETURN_REASON), "cross-town")
        for key, reason in emitted[1:]:
            # Every step of the return is a walk (optionally carrying the Inn's
            # own destination selection); the mine phase never spends a scroll.
            self.assertTrue(key[:1] in set("12346789"), (key, reason))
            self.assertFalse(key.startswith(READ_KEY), key)

    def test_p1_empty_procurement_stop_returns_to_the_outpost(self):
        self._assert_cross_town_return_replaces_the_wander(EMPTY_STOP)

    def test_p2_destruction_procurement_stop_returns_to_the_outpost(self):
        self._assert_cross_town_return_replaces_the_wander(DESTRUCTION_STOP)

    def test_p5_unaffordable_return_still_names_the_missing_entrance(self):
        """The fallback: the return is refused, so the stop names the cause.

        The same recorded boards with the Inn fare (TOWN_TELEPORT_COST) out of
        reach.  Nothing else on the page changes: the mining kit is complete
        either way, so the Alchemist still wants nothing.
        """
        emitted = self._drive(EMPTY_STOP, gold=TOWN_TELEPORT_COST - 1)
        reasons = [reason for _key, reason in emitted]
        self.assertNotIn("stuck:wander", reasons)
        self.assertNotIn("town:blocked:owner-retired", reasons)
        self.assertNotIn(RETURN_REASON, reasons)
        self.assertEqual(reasons[1], BLOCKED_REASON)
        self.assertIn(BLOCKED_REASON, POLICY_FINAL_STOP_REASONS)
        # The driver stops there instead of deciding again.
        self.assertEqual(len(emitted), 2)

    def test_p6_a_town_zero_mining_wander_is_left_alone(self):
        """A mine plan in the Outpost still has a walk-in goal.

        Same seam, same winning rung, a town whose emitted board carries the
        Yeek Cave entrance: the walk-in goal exists, so neither the cross-town
        return nor the blocked stop can apply and the pre-existing owner keeps
        the decision.  The walk-in itself is pinned where it already was
        (tests/test_policy_town.py
        ``test_mining_walk_in_is_the_only_zero_recall_entry`` and the descent
        pins in tests/test_policy_navigation.py).
        """
        entrance = Position(30, 92)
        here = Position(30, 90)
        grids = {
            Position(30, x): grid(30, x) for x in range(88, 94)
        }
        grids[entrance] = grid(
            entrance.y, entrance.x, entrance=True,
            entrance_dungeon_id=DUNGEON_YEEK_CAVE,
        )
        board = Snapshot(
            player(here.y, here.x, class_id=PLAYER_CLASS_WARRIOR, gold=5398),
            grids, [], floor_key=(0, 0, 0), inventory=[], equipment=[],
            town_id=OUTPOST_TOWN_ID,
        )
        with TemporaryDirectory() as raw_directory:
            policy = self._fresh_policy(Path(raw_directory))
            policy.prime(board)
            policy._fundraising_mode = "mine"
            known = policy.with_known_skill_exp(board)
            self.assertEqual(policy._town_walk_in_entrance(known), entrance)

            policy.last_reason = "stuck:wander"
            policy._town_procurement_decision(known, "6")

            self.assertNotIn(policy.last_reason, {RETURN_REASON, BLOCKED_REASON})
            self.assertNotEqual(
                policy._town_blocked_reason, "walk-in-entrance-unavailable"
            )

    # -- P3 --------------------------------------------------------------
    def test_the_new_stop_reason_is_registered_everywhere_it_is_read(self):
        """Reason census: owner family, final-stop set and operator banner."""
        from hengbot.cli import _policy_final_stop_banner

        self.assertEqual(reason_owner_family(BLOCKED_REASON), "town-plan")
        self.assertIn(BLOCKED_REASON, POLICY_FINAL_STOP_REASONS)
        self.assertIn(BLOCKED_REASON, _policy_final_stop_banner(BLOCKED_REASON))

    def test_p3_a_live_shop_errand_still_buys_from_the_same_page(self):
        """The same recorded Alchemist page, with its errand still live.

        The recorded process had already bought its five treasure-detection
        scrolls for the one planned mining run (decision 15 of the same visit,
        gold 5518 -> 5398), which is why its page wanted nothing.  Without that
        run count the mining kit rung still wants them, so the same page is
        shopped and bought before anything else; only once that errand is
        served does the same honest terminal follow.
        """
        emitted = self._drive(EMPTY_STOP, planned_mining_runs=False)
        reasons = [reason for _key, reason in emitted]
        # The live errand owns the board: the new terminal cannot preempt it.
        self.assertNotIn(BLOCKED_REASON, reasons[:3])
        self.assertTrue(
            all(reason.startswith(("shop:", "town-progress-invariant:"))
                for reason in reasons[:3]),
            reasons,
        )
        self.assertIn("shop:one-shot-buy", reasons)


if __name__ == "__main__":
    unittest.main()
