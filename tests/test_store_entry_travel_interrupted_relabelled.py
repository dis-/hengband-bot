"""Recorded pins: native store travel posted under a relabelled owner.

2026-09-23 01:43 (protocol 3): decision 1905 posted native travel to the
Alchemist under the town progress invariant's relabelled reason.  Travel
stopped 20 cells short, next to a sleeping town monster.  Decision 1906 then
waited for a store page that could never arrive (key '', reason
store:entry-await-observation) and the driver stopped with no-key-exhausted.

Fixture: tests/fixtures/store-entry-travel-interrupted-20260923.jsonl.gz,
written by tests/extract_store_entry_travel_interrupted_fixture.py.

pin_vacuity: the capture holds boards and decision facts, not a restorable
policy.  Each pin therefore runs the production producer of the posted travel
(_shopping_approach_step + _shopping_approach_key on the recorded input board
of the posting decision) and must reproduce the recorded key before the
recorded next board is decided through public choose_key.  JSONL rows never
carry the executor's barrier binding (input_executor.py stamps it only on the
barrier board), so the posting decision's recorded (sequence, reason) is
re-attached to the recorded next board exactly as the executor would.
"""

import gzip
import json
import unittest
from pathlib import Path

import tests  # noqa: F401  (bare runs stay isolated from runtime files)
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisitPhase


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    ROOT / "tests" / "fixtures" /
    "store-entry-travel-interrupted-20260923.jsonl.gz"
)
EDIT = Path("C:/hengband/lib/edit")
ALCHEMIST = 4
WEAPONSMITH = 2
ALCHEMIST_TRAVEL = "\x1b`n%."
WEAPONSMITH_TRAVEL = "\x1b`n#."
RELABELLED_OWNER = (
    "town-progress-invariant:defect:shop:travel:await-entry"
    "=>town-progress-invariant:approach"
)


def _records():
    with gzip.open(FIXTURE, "rb") as stream:
        return [json.loads(line) for line in stream]


class RelabelledStoreTravelInterruptionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        records = _records()
        cls.skill = {r["board"]["turn"]: r["board"] for r in records
                     if r["role"] == "skill-knowledge"}
        cls.inputs = {r["decision"]["decision_sequence"]: r for r in records
                      if r["role"] == "decision-input"}
        cls.lagged = next(r for r in records if r["role"] == "lagged-duplicate")

    def _posted_travel(self, sequence, skill_turn, store_type, travel_reason):
        """Reproduce the recorded native-travel post of ``sequence``."""
        record = self.inputs[sequence]
        policy = HengbotPolicy(monrace_knowledge=self.monrace)
        board = parse_snapshot(record["board"], self.monrace)
        policy.prime(board)
        policy.consume_skill_knowledge(self.skill[skill_turn])
        policy._decision_sequence = sequence
        step = policy._shopping_approach_step(board, store_type)
        self.assertIsNotNone(step)
        key = policy._shopping_approach_key(board, step, travel_reason)
        self.assertEqual(str(key), record["decision"]["key"])
        policy.last_reason = record["decision"]["reason"]
        self.assertTrue(policy.confirm_key_posted(key))
        visit = policy._store_visit
        self.assertEqual(
            (visit.store_type, visit.phase, visit.posted_sequence),
            (store_type, StoreVisitPhase.ENTERING, sequence),
        )
        return policy

    def _barrier_board(self, sequence, row):
        """The recorded next board as the executor's barrier returns it."""
        bound = dict(row)
        bound["_completed_operation_sequence"] = sequence
        bound["_completed_operation_owner"] = (
            self.inputs[sequence]["decision"]["reason"]
        )
        return parse_snapshot(bound, self.monrace)

    def test_fixture_freezes_recorded_incident_facts(self):
        posted = self.inputs[1905]["decision"]
        self.assertEqual(
            (posted["key"], posted["reason"], posted["turn"]),
            (ALCHEMIST_TRAVEL, RELABELLED_OWNER, 4_734_443),
        )
        waited = self.inputs[1906]["decision"]
        self.assertEqual(
            (waited["key"], waited["reason"], waited["turn"]),
            ("", "store:entry-await-observation", 4_734_609),
        )
        self.assertEqual(
            waited["town_emit_ownership"]["in_flight_clause"],
            "entering-with-posted-sequence",
        )
        self.assertEqual(
            (waited["store_visit"]["store_type"],
             waited["store_visit"]["phase"],
             waited["store_visit"]["posted_sequence"]),
            (ALCHEMIST, "entering", 1905),
        )
        self.assertEqual(waited["loot_blocker"], "adjacent-hostile")
        self.assertEqual(waited["threat_monsters"], [{
            "race_id": 13, "position": {"y": 43, "x": 103},
            "distance": 1, "asleep": True,
        }])
        board = parse_snapshot(self.inputs[1906]["board"], self.monrace)
        self.assertIsNone(board.store)
        self.assertEqual(
            (board.player.position.y, board.player.position.x), (44, 103)
        )
        entrances = [
            (grid.position.y, grid.position.x)
            for grid in board.grids.values()
            if grid.store_number == ALCHEMIST
        ]
        self.assertEqual(entrances, [(37, 91)])
        self.assertEqual(board.grid_at(board.player.position).store_number, -1)

    def test_s1_relabelled_interrupted_travel_replans_instead_of_waiting(self):
        policy = self._posted_travel(
            1905, 4_733_303, ALCHEMIST, "town-progress-invariant:approach"
        )
        self.assertEqual(
            (policy._town_travel_state.goal.y, policy._town_travel_state.goal.x),
            (37, 91),
        )
        interrupted = self._barrier_board(1905, self.inputs[1906]["board"])
        key = policy.choose_key(interrupted)
        self.assertNotEqual(key, "")
        self.assertEqual(
            (str(key), policy.last_reason),
            (ALCHEMIST_TRAVEL, "store:entry-interrupted-replan"),
        )
        self.assertIsNone(policy._store_visit.posted_sequence)
        self.assertEqual(policy._store_visit.store_type, ALCHEMIST)

    def test_s2_unobserved_post_still_waits_for_entry_observation(self):
        policy = self._posted_travel(
            1905, 4_733_303, ALCHEMIST, "town-progress-invariant:approach"
        )
        lagged = parse_snapshot(self.lagged["board"], self.monrace)
        self.assertIsNone(lagged.completed_operation_sequence)
        self.assertEqual(lagged.turn, 4_734_443)
        key = policy.choose_key(lagged)
        self.assertEqual(
            (str(key), policy.last_reason),
            ("", "store:entry-await-observation"),
        )
        self.assertEqual(policy._store_visit.posted_sequence, 1905)
        self.assertEqual(policy._store_visit.phase, StoreVisitPhase.ENTERING)

    def test_s3_travel_that_opens_the_store_page_proceeds_into_the_store(self):
        policy = self._posted_travel(
            1719, 4_730_301, WEAPONSMITH, "shop:travel"
        )
        self.assertEqual(self.inputs[1719]["decision"]["key"], WEAPONSMITH_TRAVEL)
        arrived = self._barrier_board(1719, self.inputs[1720]["board"])
        self.assertEqual(arrived.store.store_type, WEAPONSMITH)
        key = policy.choose_key(arrived)
        recorded = self.inputs[1720]["decision"]
        # Same decision as recorded live: observe the page and leave.
        self.assertEqual(
            (str(key), policy.last_reason),
            (recorded["key"], recorded["reason"]),
        )
        self.assertEqual(
            (str(key), policy.last_reason),
            ("\x1b", "town-progress-invariant:continue-observed-shop"),
        )
        self.assertEqual(policy._store_visit.store_type, WEAPONSMITH)
        self.assertEqual(policy._store_visit.phase, StoreVisitPhase.LEAVING)


if __name__ == "__main__":
    unittest.main()
