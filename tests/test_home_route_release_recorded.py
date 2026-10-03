"""Capture pins for the 234018/234047/234116 legacy Home deposit handoff.

DECLARED CONSTRUCTED: no onset policy checkpoint was retained. The immutable
store/outside boards are real; the pending ledger and Home executor are rebuilt
from the posted do28\\rdl\\x1b command (28 arrows and the slot-l sword). Later
unchanged boards are constructed waits, not replayed historical decisions after
a changed key. The actual choose_key and ownership gates run without patches.
"""
import gzip
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import unittest

import tests  # noqa: F401
from hengbot.claim_register import observe
from hengbot.emit_ownership import in_flight_clause
from hengbot.home_visit import HomeVisitKind, HomeVisitRequest as PhysicalHomeVisitRequest
from hengbot.model import parse_snapshot, STORE_HOME, Position
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import STORE_STUCK_LIMIT
from hengbot.policy_types import StoreVisit, StoreVisitPhase
from policy_fixtures import grid
from test_s33_batch_admission import corridor
from test_s33_batch_context import captured_session

FIXTURE = Path(__file__).parent / "fixtures/home-route-release-20261003.json.gz"


def reconstructed(pin, enforced):
    before, after = parse_snapshot(pin["before"]), parse_snapshot(pin["after"])
    # DECLARED CONSTRUCTED corridor removes unrelated town movement ties.
    # The item facts and posted/observed turns stay exactly as captured.
    after = replace(corridor(), turn=after.turn, inventory=after.inventory,
                    equipment=after.equipment,
                    player=replace(after.player, position=Position(10, 10)),
                    grids={**corridor().grids, Position(10, 14):
                           replace(grid(10, 14), store_number=STORE_HOME)})
    policy = HengbotPolicy()
    policy.prime(after)
    policy.consume_skill_knowledge(pin["skill_knowledge"])
    policy._town_claim_bar_enforced = enforced
    policy._decision_sequence = 3
    key = "do28\rdl\x1b"
    targets = (before.inventory[14], before.inventory[11])
    entries = tuple((policy._item_signature(item), item.count, item.count)
                    for item in targets)
    policy._home_atomic_deposit_pending = (entries, None, before.turn, 0)
    policy._home_entry_operation_posted = True
    policy._store_visit = StoreVisit(
        "town-errand", "shopping", STORE_HOME, StoreVisitPhase.OPERATING,
        opened_sequence=2, posted_sequence=3, posted_turn=before.turn,
        operation_posted=True, operation_released=True,
        operation_key=key, operation_producer_family="home-visit",
        claim_operation_identity=(STORE_HOME, 2, key))
    visit = policy._home_visit
    visit.file(PhysicalHomeVisitRequest(HomeVisitKind.DEPOSIT,
               "weight-overload", entries[0][0], quantity=28))
    visit.begin_approach(2)
    policy._prepare_home_visit_operation("put", entries[0][0], ("captured-pack",))
    claim = policy._claim_register.declare("home-visit",
        observe((STORE_HOME, 2, key), STORE_STUCK_LIMIT, source="store-operation"),
        floor=after.floor_key)
    policy._claim_register.declare_execution(claim.claim_id, producer="home-visit",
        work_id=f"home-operation:2:{key}", state="acting",
        next_step="home.operation.send", expected_effect="home-inventory-effect",
        continuation="home.operation.observe", budget_ref="home-operation-existing-budget")
    return policy, before, after, entries


class HomeRouteReleaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == "31ad6e4413b6d1681e176d63a6467aa3571c8d3a08bc1a50435e181278596302"
        cls.pins = json.loads(gzip.decompress(FIXTURE.read_bytes()))

    def test_recorded_deposit_was_refused_with_home_at_capacity(self):
        for pin in self.pins:
            self.assertEqual(pin["before"]["inventory"], pin["after"]["inventory"])
            self.assertEqual(pin["before"]["store"], pin["refused"]["store"])
            self.assertEqual(pin["before"]["store"]["stock_num"], 240)
            self.assertEqual(pin["before"]["store"]["capacity"], 240)
            self.assertTrue(pin["refused"]["messages"])
            self.assertEqual(len(pin["catalogue_before"]), 240)
            self.assertEqual(pin["catalogue_before"], pin["catalogue_after"])

    def test_failed_deposit_observes_before_equipment_and_hands_off_once(self):
        for pin in self.pins:
            for enforced in (False, True):
                with self.subTest(stamp=pin["stamp"], enforced=enforced):
                    self._assert_failed_deposit_episode(pin, enforced)

    def _assert_failed_deposit_episode(self, pin, enforced):
        # Each episode starts a fresh constructed checkpoint. Its only repeated
        # boards follow asserted stationary WAITs; the first movement ends it.
        policy, before, after, entries = reconstructed(pin, enforced)
        _, session = captured_session(pin["stamp"],
            {"234018": 224, "234047": 223, "234116": 219}[pin["stamp"]])
        policy._equipment_transaction_session = session
        old_visit = policy._store_visit
        for count in range(1, STORE_STUCK_LIMIT):
            board = replace(after, turn=after.turn + count)
            key = policy.choose_key(board)
            self.assertEqual(key, "5")
            self.assertEqual(policy.last_reason, "home:atomic-deposit-await-confirmation")
            self.assertIsNone(policy.decision_claim["declaration_mismatch"])
            self.assertIsNone(policy.decision_claim["claim_verdict_conflict"])
            self.assertIsNone(policy.decision_claim["violation"])
            self.assertIsNone(policy._s33_shadow_verdict(board, key)["would_stop"])
            self.assertEqual(policy._home_atomic_deposit_pending[3], count)
            self.assertEqual(in_flight_clause(old_visit),
                             "operation-released-effect-not-observed")
        policy.choose_key(replace(after, turn=after.turn + STORE_STUCK_LIMIT))
        self.assertIs(policy._equipment_transaction_session, session)
        self.assertFalse(session.blockers)
        self.assertEqual(policy.last_reason, "equipment-transaction:travel-home")
        self.assertIsNone(policy._home_atomic_deposit_pending)
        self.assertIsNone(policy.decision_claim["declaration_mismatch"])
        self.assertIsNone(policy.decision_claim["claim_verdict_conflict"])
        self.assertEqual(old_visit.outcome, "home-deposit-unobserved")
        self.assertIsNone(in_flight_clause(old_visit))
        self.assertFalse(old_visit.operation_effect_observed)
        self.assertTrue({entry[0] for entry in entries}
                        <= policy._home_rejected_deposits)
        self.assertNotEqual(policy.last_reason,
                            "equipment-transaction:home-route-repeat-terminal")
        refusal = policy.home_route_refusal_state()
        self.assertFalse(refusal and refusal["executor_state"] == "EXIT_PENDING")


    def test_observed_delta_closes_before_bookkeeping(self):
        pin = self.pins[0]
        policy, before, after, entries = reconstructed(pin, False)
        old_visit = policy._store_visit
        # DECLARED CONSTRUCTED successful alternative: remove precisely the
        # recorded command's two targets. This is not the historical outcome.
        board = replace(after, inventory=tuple(item for item in after.inventory
                        if policy._item_signature(item) not in {e[0] for e in entries}))
        policy.choose_key(board)
        self.assertIsNone(policy._home_atomic_deposit_pending)
        self.assertTrue(old_visit.operation_effect_observed)
        self.assertIsNone(in_flight_clause(old_visit))

    def test_unreleased_or_same_turn_board_cannot_confirm_or_charge(self):
        for unreleased in (False, True):
            policy, before, after, entries = reconstructed(self.pins[0], False)
            if unreleased:
                policy._store_visit.operation_released = False
            board = after if unreleased else replace(after, turn=before.turn)
            policy.choose_key(board)
            self.assertEqual(policy._home_atomic_deposit_pending[3], 0)
            self.assertFalse(policy._store_visit.operation_effect_observed)


    def test_survival_can_interrupt_pending_observation(self):
        policy, before, after, entries = reconstructed(self.pins[0], True)
        key = policy.choose_key(replace(after, player=replace(after.player, hp=1)))
        self.assertTrue(policy.decision_claim["survival"])
        self.assertIsNone(policy.decision_claim["declaration_mismatch"])
        self.assertIsNone(policy.decision_claim["claim_verdict_conflict"])
        self.assertEqual(policy._home_atomic_deposit_pending[3], 1)
        self.assertNotEqual(key, "5")
