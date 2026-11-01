"""#47: the remaining town walks ride the game's travel command (owner
2026-11-01 「街での移動は可能な限りトラベルコマンドを活用して」, deferred by D52
me-tower-trips-1101 as its question 3).

D52 (town_travel) moved the Tower, every inn leg without a decision context
and the rumor walk onto travel.  Four walks still stepped one cell per
decision; each recorded board below goes through the public choose_key and
the chosen key through the production executor (test_me_nokey_1031_recorded
.PostedKey, the game's 256-key queue):

- fixedquest:q22-travel (the declared route to Morivant's inn), recorded
  incident 2026-09-13 (tests/fixtures/quest-request-retired-stage1.jsonl.gz,
  turn 2856171: the walk stepped one cell per decision, ranks 10 -> 6).
- fixedquest:prepare-return with its route declaration (return-3), recorded
  town-3 walk (tests/fixtures/quest-prepare-return-town3-walk-stage2.jsonl.gz,
  turn 2856703: '7', '8', '9', '9', '9'; n1-c life-074 5197-5210 walked the
  same producer 14 cells).
- bounty:approach (the Hunter's office), recorded live22
  (tests/fixtures/live22-bounty, decision 5123: '7').
- town:morivant-full-identify:library (Morivant's Inn to its Library), the
  recorded n1-a life-433 session (tests/fixtures/
  morivant-library-identify-20261030.json.gz, decisions 7678-7691: 14 single
  steps '1', '1', '2', '3', ...).

Each travels to the cell beside its building (town_travel.building_key);
the step into the building and its command tail stay the producer's own.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import unittest

from hengbot.model import parse_snapshot
from hengbot.policy_types import DecisionCandidate
from hengbot.town_travel import is_travel_macro
from tests import test_live22_bounty as live22
from tests import test_me_nokey_1031_recorded as nokey
from tests.test_quest_travel_progress import ROOT, QuestTravelFixtureMixin

PREPARE_RETURN = ROOT / "tests/fixtures/quest-prepare-return-town3-walk-stage2.jsonl.gz"
FIRST_RETURN_TURN = 2856703


class TravelBeside:
    def assert_travel_beside(self, policy, key, building, reason):
        self.assertEqual(policy.last_reason, reason, key)
        self.assertTrue(is_travel_macro(str(key)), (key, policy.last_reason))
        self.assertEqual(policy._town_travel_state.goal.distance_to(building), 1)


class QuestTravelRecordedTest(TravelBeside, QuestTravelFixtureMixin, nokey.PostedKey):
    setUpClass = classmethod(QuestTravelFixtureMixin.setUpClass.__func__)

    def test_q22_travel_rides_the_travel_command_to_the_inn(self):
        policy = self._policy()
        for number, raw, line in self._records():
            if raw.get("type") in {"knowledge", "look", "character"}:
                self._dispatch(policy, line)
                continue
            snapshot = parse_snapshot(raw, self.monrace)
            if number == 4:
                policy.prime(snapshot)
            key = policy.choose_key(snapshot)
            if policy.last_reason == "fixedquest:q22-travel":
                break
            policy.confirm_key_posted(key)
        self.assertEqual(snapshot.turn, 2856171)
        declaration = key.route_declaration
        self.assertIsInstance(key, DecisionCandidate)
        # Unfixed: '7', the recorded single step.
        self.assert_travel_beside(policy, key, declaration.goal, "fixedquest:q22-travel")
        self.assertEqual((declaration.composed_key, declaration.bfs_rank), (str(key), 10))
        self.post(policy, raw, str(key))

    def test_declared_prepare_return_rides_the_travel_command_to_the_inn(self):
        policy = self._policy()
        with gzip.open(PREPARE_RETURN, "rt", encoding="utf-8") as stream:
            records = [json.loads(line) for line in stream]
        for index, raw in enumerate(records):
            snapshot = parse_snapshot(raw, self.monrace)
            if index == 0:
                policy.prime(snapshot)
            key = policy.choose_key(snapshot)
            if raw["turn"] >= FIRST_RETURN_TURN:
                break
            policy.confirm_key_posted(key)
        declaration = key.route_declaration
        self.assertEqual((declaration.producer_branch, declaration.composed_key),
                         ("return-3", str(key)))
        # Unfixed: '7' (the recorded walk 7, 8, 9, 9, 9).
        self.assert_travel_beside(policy, key, declaration.goal, "fixedquest:prepare-return")
        self.post(policy, raw, str(key))


class BountyApproachRecordedTest(TravelBeside, nokey.PostedKey):
    def test_office_walk_rides_the_travel_command(self):
        policy, recorded = live22.attached_policy()
        board = recorded[0]
        # The captured process already held the skill knowledge.
        policy.consume_skill_knowledge({
            "player": {"level": board.player.level},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        key = policy.choose_key(board)
        # Unfixed: '7' (recorded decision 5123).
        self.assert_travel_beside(policy, key, live22.OFFICE, "bounty:approach")
        # The office's own work stays the declared continuation.
        self.assertEqual(policy._claim_register.current.execution.continuation, "bounty.resume")
        with gzip.open(live22.FIXTURE / "state.jsonl.gz", "rt", encoding="utf8") as source:
            raw = json.loads(next(source))
        self.post(policy, raw, key)


if __name__ == "__main__":
    unittest.main()
