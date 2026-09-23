"""Recorded pins: a posted store operation must reach a bounded conclusion.

Three stops in 2h30 of runtime on 2026-09-23, all with a store operation whose
effect was never observed:

  18:15 town:blocked:owner-retired - a queued Home take (_home_pending_item)
        was handed off to the outside composer, which refuses without a
        current Home catalogue; the only producer of that catalogue is the
        Home page the hand-off just left.  The bot cycled Home ->
        home:leave-for-pending-withdraw -> an approach step whose reason was
        the EMPTY STRING -> shop:approach -> Home, until the arbiter retired
        the owner.
  20:10 stuck-prompt - the town progress invariant replaced the Home page's
        leave with "Eh" (survival:mana-absorb), which the store rejects
        ("that command cannot be used in a store").  The escape therefore
        never reached the game, but the visit had already been armed as
        LEAVING, so shop:await-leave-confirmation repeated its no-op "\\r"
        forever: that key cannot advance the turn, which is the only exit the
        wait had.
  20:26 no-key-exhausted - the composed Alchemist one-shot returned the
        stay key that enters the store, and _forbid_wait_while_damaged
        replaced it with a Teleport scroll read (no-wait:escape-scroll).  The
        macro was never posted, the player teleported across town, and the
        entering wait emitted no key for a store page that could never arrive.

Fixture: tests/fixtures/posted-effect-unobserved-20260923.jsonl.gz, written by
tests/extract_posted_effect_unobserved_fixture.py (provenance beside it names
both source files of each capture by sha256, and how the byte rings are read).

pin_vacuity: the captures hold boards, decision facts and a JSON state dump,
not a restorable policy checkpoint.  Each pin therefore runs the production
producer on the recorded input board of the recorded decision, with exactly the
recorded pre-decision facts re-attached (the recorded StoreVisit fields, the
recorded shopping-approach target, and for 18:15 the named policy-state fields
the fixture freezes), in the manner of the store-entry-travel-interrupted pins.
Every pin first asserts the recorded stop it reproduces.
"""

import gzip
import json
import unittest
from pathlib import Path

import tests  # noqa: F401  (bare runs stay isolated from runtime files)
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import STORE_STUCK_LIMIT
from hengbot.policy_types import StoreVisit, StoreVisitPhase


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    ROOT / "tests" / "fixtures" / "posted-effect-unobserved-20260923.jsonl.gz"
)
EDIT = Path("C:/hengband/lib/edit")
HOME_CYCLE = "20260923-181527-town-blocked-owner-retired"
LEAVE_REPEAT = "20260923-201024-stuck-prompt"
ONE_SHOT = "20260923-202618-no-key-exhausted"
STORE_HOME = 7
ALCHEMIST = 3
WAIT_KEY = "5"
LEAVE_STORE_KEY = "\x1b"


def _records():
    with gzip.open(FIXTURE, "rb") as stream:
        return [json.loads(line) for line in stream]


class PostedEffectUnobservedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
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
    def _board(self, capture, sequence):
        return parse_snapshot(self.inputs[(capture, sequence)]["board"], self.monrace)

    def _decision(self, capture, sequence):
        return self.inputs[(capture, sequence)]["decision"]

    def _policy(self, capture, board, sequence):
        policy = HengbotPolicy(monrace_knowledge=self.monrace)
        policy.prime(board)
        policy.consume_skill_knowledge(self.skill[capture])
        policy._decision_sequence = sequence
        return policy

    def _recorded_visit(self, capture, sequence, **overrides):
        """The StoreVisit exactly as the recorded decision carried it."""
        recorded = dict(self._decision(capture, sequence)["store_visit"])
        visit = StoreVisit(
            owner=recorded["owner"],
            purpose=recorded["purpose"],
            store_type=recorded["store_type"],
            phase=StoreVisitPhase(recorded["phase"]),
            visit_origin=recorded["visit_origin"],
            opened_sequence=recorded["opened_sequence"],
            posted_sequence=recorded["posted_sequence"],
            posted_turn=recorded["posted_turn"],
            operation_posted=recorded["operation_posted"],
            operation_released=recorded["operation_released"],
            operation_effect_observed=recorded["operation_effect_observed"],
        )
        for name, value in overrides.items():
            setattr(visit, name, value)
        return visit

    # -- the recorded stops ----------------------------------------------
    def test_fixture_freezes_the_three_recorded_stops(self):
        cycle_leave = self._decision(HOME_CYCLE, 1567)
        self.assertEqual(
            (cycle_leave["key"], cycle_leave["reason"], cycle_leave["store_type"]),
            (LEAVE_STORE_KEY, "home:leave-for-pending-withdraw", STORE_HOME),
        )
        unnamed = self._decision(HOME_CYCLE, 1568)
        # A decision that emits a key with no reason: neither the reason
        # census nor the town arbiter can classify it.
        self.assertEqual((unnamed["key"], unnamed["reason"]), ("9", ""))
        self.assertEqual(unnamed["arbiter"]["decision_attribution"], "misc")
        self.assertEqual(self._decision(HOME_CYCLE, 1569)["reason"], "shop:approach")
        self.assertEqual(
            self._decision(HOME_CYCLE, 1570)["reason"],
            "home:leave-for-pending-withdraw",
        )
        self.assertEqual(
            self.state[HOME_CYCLE],
            {
                "_home_pending_item": ["鑑定の杖 (2x 18回分)", 55, 5],
                "_home_pending_quantity": 1,
                "_home_knowledge_current": False,
                "_home_knowledge_valid_before": 0,
                "_home_scan_source": None,
                "_home_scan_item_count": None,
            },
        )

        substituted = self._decision(LEAVE_REPEAT, 5428)
        self.assertEqual(
            (substituted["key"], substituted["reason"]),
            (
                "Eh",
                "town-progress-invariant:defect:"
                "home:queue-withdraw-identify-staff-reserve=>survival:mana-absorb",
            ),
        )
        repeated = self._decision(LEAVE_REPEAT, 5429)
        self.assertEqual(
            (repeated["key"], repeated["reason"]),
            ("\r", "shop:await-leave-confirmation"),
        )
        # The store refused the substituted command, so the page and the turn
        # are unchanged - the only exit the confirmation wait has.
        self.assertEqual(
            repeated["messages"],
            [
                "そのコマンドは店の中では使えません。",
                "そのコマンドは店の中では使えません。 <x2>",
            ],
        )
        self.assertEqual(substituted["turn"], repeated["turn"])
        self.assertEqual(
            repeated["town_emit_ownership"]["in_flight_clause"],
            "leaving-with-posted-sequence",
        )

        posted = self._decision(ONE_SHOT, 629)
        self.assertEqual((posted["key"], posted["reason"]), ("re", "no-wait:escape-scroll"))
        self.assertEqual(posted["store_visit"]["operation_posted"], True)
        stranded = self._decision(ONE_SHOT, 630)
        self.assertEqual(
            (stranded["key"], stranded["reason"]), ("", "shop:one-shot-in-flight")
        )
        self.assertEqual(
            stranded["town_emit_ownership"]["in_flight_clause"],
            "operation-posted-not-released",
        )
        # The stranded wait is at the other end of town from the Alchemist it
        # is waiting for; the escape scroll moved the player there.
        self.assertEqual(posted["position"], {"y": 24, "x": 88})
        self.assertEqual(stranded["position"], {"y": 53, "x": 14})

    # -- P1 --------------------------------------------------------------
    def test_p1_posted_one_shot_away_from_its_entrance_concludes(self):
        board = self._board(ONE_SHOT, 630)
        policy = self._policy(ONE_SHOT, board, 630)
        policy._shopping_approach_store_type = ALCHEMIST
        policy._store_visit = self._recorded_visit(
            ONE_SHOT, 630, operation_key="pl" + LEAVE_STORE_KEY, composed_key=WAIT_KEY,
        )
        here = board.grid_at(board.player.position)
        self.assertNotEqual(here.store_number, ALCHEMIST)
        self.assertGreater(board.turn, policy._store_visit.posted_turn)

        key = policy.choose_key(board)

        self.assertIsNotNone(key)
        self.assertNotEqual(str(key), "")
        self.assertNotEqual(policy.last_reason, "shop:one-shot-in-flight")
        self.assertEqual(
            policy._store_visit_last_closed.outcome, "one-shot-entrance-left"
        )

    def test_p4_posted_one_shot_still_waits_at_its_own_entrance(self):
        """The legitimate wait is unchanged (pin: test_shop_one_shot.

        ShopOneShotTest.test_stage_two_refuses_stale_store_page, and
        test_store_entry_travel_interrupted_relabelled
        .test_s2_unobserved_post_still_waits_for_entry_observation).
        """
        board = self._board(ONE_SHOT, 629)
        policy = self._policy(ONE_SHOT, board, 630)
        policy._shopping_approach_store_type = ALCHEMIST
        policy._store_visit = self._recorded_visit(
            ONE_SHOT, 630, operation_key="pl" + LEAVE_STORE_KEY, composed_key=WAIT_KEY,
        )
        here = board.grid_at(board.player.position)
        self.assertEqual(here.store_number, ALCHEMIST)
        self.assertEqual(board.turn, policy._store_visit.posted_turn)

        key = policy.choose_key(board)

        self.assertEqual((str(key), policy.last_reason), ("", "shop:one-shot-in-flight"))
        self.assertEqual(policy._store_visit.phase, StoreVisitPhase.ENTERING)
        self.assertTrue(policy._store_visit.operation_posted)

    # -- P2 --------------------------------------------------------------
    def test_p1b_rewritten_store_key_releases_the_posting_it_armed(self):
        """The 20:10 substitution no longer strands the visit it armed."""
        board = self._board(LEAVE_REPEAT, 5428)
        policy = self._policy(LEAVE_REPEAT, board, 5428)
        policy._shopping_approach_store_type = STORE_HOME
        policy._store_visit = self._recorded_visit(LEAVE_REPEAT, 5427 + 1)
        policy._store_visit.phase = StoreVisitPhase.ENTERING
        policy._store_visit.posted_sequence = None
        policy._store_visit.posted_turn = None

        key = policy.choose_key(board)

        recorded = self._decision(LEAVE_REPEAT, 5428)
        # The same substitution the capture recorded still happens ...
        self.assertEqual((str(key), policy.last_reason),
                         (recorded["key"], recorded["reason"]))
        # ... but the escape it replaced is no longer treated as posted.
        self.assertIsNone(policy._store_visit)
        self.assertEqual(
            policy._store_visit_last_closed.outcome, "posting-rewritten"
        )

    def test_p2_leave_confirmation_ends_within_its_bound(self):
        board = self._board(LEAVE_REPEAT, 5429)
        policy = self._policy(LEAVE_REPEAT, board, 5429)
        policy._shopping_approach_store_type = STORE_HOME
        policy._store_visit = self._recorded_visit(
            LEAVE_REPEAT, 5429, composed_key=LEAVE_STORE_KEY,
        )
        generation = policy._store_visit.posted_sequence
        self.assertEqual(policy._store_leave_inflight,
                         (generation, board.turn, STORE_HOME))

        # The recorded board is re-decided unchanged on purpose: the store
        # refused the substituted command, so neither the page nor the turn
        # moved, which is exactly the state this wait could not leave.
        waits = 0
        released = None
        for _ in range(4 * STORE_STUCK_LIMIT):
            key = policy.choose_key(board)
            if policy.last_reason == "shop:await-leave-confirmation":
                waits += 1
                self.assertEqual(str(key), "\r")
            closed = policy._store_visit_last_closed
            if closed is not None:
                released = closed
                break
            policy._decision_sequence += 1

        self.assertIsNotNone(released, "the confirmation wait never ended")
        self.assertEqual(released.outcome, "leave-unconfirmed")
        self.assertLessEqual(waits, STORE_STUCK_LIMIT)
        self.assertLessEqual(
            policy._decision_sequence - generation, STORE_STUCK_LIMIT
        )

    # -- P3 --------------------------------------------------------------
    def _home_cycle_policy(self):
        inside = self._board(HOME_CYCLE, 1567)
        policy = self._policy(HOME_CYCLE, inside, 1567)
        fields = self.state[HOME_CYCLE]
        policy._shopping_approach_store_type = STORE_HOME
        policy._home_pending_item = tuple(fields["_home_pending_item"])
        policy._home_pending_quantity = fields["_home_pending_quantity"]
        policy._home_knowledge_current = fields["_home_knowledge_current"]
        policy._store_visit = self._recorded_visit(
            HOME_CYCLE, 1567, phase=StoreVisitPhase.ENTERING,
            posted_sequence=None, posted_turn=None,
        )
        return policy, inside, self._board(HOME_CYCLE, 1568)

    def test_p3_queued_home_take_refreshes_the_catalogue_it_needs(self):
        policy, inside, outside = self._home_cycle_policy()
        self.assertFalse(policy._home_knowledge_current)

        board = inside
        reasons = []
        for _ in range(6):
            policy.choose_key(board)
            reasons.append(policy.last_reason)
            board = outside if board is inside else inside

        # The hand-off that could never be composed is gone ...
        self.assertNotIn("home:leave-for-pending-withdraw", reasons)
        # ... and the bot asks for the catalogue the outside composer needs
        # within the first two Home entries, instead of leaving again.
        self.assertIn("home:request-knowledge-scan", reasons)
        self.assertLessEqual(reasons.index("home:request-knowledge-scan"), 3)

    def test_p3_no_decision_is_emitted_without_a_reason(self):
        policy, inside, outside = self._home_cycle_policy()
        self.assertEqual(self._decision(HOME_CYCLE, 1568)["reason"], "")

        board = inside
        emitted = []
        for _ in range(6):
            key = policy.choose_key(board)
            emitted.append((str(key) if key is not None else None, policy.last_reason))
            board = outside if board is inside else inside

        self.assertEqual([reason for _key, reason in emitted if reason == ""], [])


if __name__ == "__main__":
    unittest.main()
