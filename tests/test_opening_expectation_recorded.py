"""n1-c life-104 2026-11-02 13:49: the opening route stopped on an unchanged board.

After the Q1 purchases each new session asked for skill-exp knowledge, then
the CLI's startup save and dump requests replaced the next safe town key.
The replaced key was the opening route's fixedquest:request:approach step,
whose producer had already posted its owner expectation (position).  That
key was never posted, so the position could not change; on the next
decision the owner yielded, _fixed_quest_key returned None and the route
stopped as quest:blocked:opening-route (quest-request-unavailable).  Three
such stops retired the character.

Pinned on the recorded board through the public chooser: the recorded
bookkeeping keys come first, then the Q1 approach step instead of the stop,
and that step is posted by the production executor.  The replies to the
bookkeeping keys are the recorded unchanged board (saving and dumping take
no game time); the reply to the step is DECLARED CONSTRUCTED.
Fixture: tests/extract_opening_expectation_1102_fixture.py.
"""
import tests  # noqa: F401

import copy
import gzip
import json
from pathlib import Path

from hengbot.model import parse_snapshot
from tests import test_opening_route_r2_recorded as round2
import tests.support.recorded as executor_harness


FIXTURE = Path(__file__).with_name("fixtures") / "opening-expectation-1102.json.gz"


class OpeningExpectationRecordedTest(executor_harness.ProductionHarness):
    # The recorded fresh-character town knowledge and the production post.
    case = round2.OpeningRouteR2RecordedTest.case
    post = round2.OpeningRouteR2RecordedTest.post
    shelf_screen = round2.OpeningRouteR2RecordedTest.shelf_screen

    @classmethod
    def setUpClass(cls):
        round2.OpeningRouteR2RecordedTest.setUpClass.__func__(cls)
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.recorded = json.load(stream)

    def test_replaced_approach_does_not_stop_the_route(self):
        recorded = self.recorded
        self.assertEqual([row["reason"] for row in recorded["decisions"]], [
            "periodic:skill-exp-knowledge", "periodic:game-save",
            "periodic:character-dump", "quest:blocked:opening-route"])
        policy, _ = self.case("1")
        raw = copy.deepcopy(recorded["board"])
        policy.prime(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        # Decision 0's reply: the recorded skill_exp knowledge row.
        policy.consume_skill_knowledge(recorded["skill"])
        # The CLI's first dump deadline is due at startup (_request_due_dump).
        policy.request_character_dump()
        policy.request_game_save()
        for row in recorded["decisions"][1:3]:
            key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
            self.assertEqual((policy.last_reason, key), (row["reason"], row["key"]))
        key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        # Recorded: "" quest:blocked:opening-route (quest-request-unavailable).
        self.assertEqual((policy.last_reason, str(key)), ("fixedquest:request:approach", "8"))
        self.assertIsNone(getattr(policy, "_opening_q1_failure", None))
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["player"]["y"] -= 1
        self.post(policy, raw, str(key), following)
