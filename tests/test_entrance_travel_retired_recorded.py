"""Recorded pins: the native-travel walk to the dungeon entrance is locomotion.

Live incident 2026-09-22 23:09:45-23:09:47 (protocol 3).  In fundraising mode
``mine`` the bot travelled to the dungeon entrance (31,150) with the native
travel macro.  The first leg moved seven cells, (45,124) -> (38,126), and
stopped beside a friendly sparrow; ``town:kill-mob-friendly`` killed it with
one ``+9y``; the travel was re-issued, and the arbiter retired the store-router
owner with ``progress False, budget 0``.  The next board stopped on
``town:blocked:owner-retired``.

Root cause: ``town:travel-entrance`` belongs to store-router, whose only goal
was the store visit's approach goal (None here).  Its progress vector was the
durable town vector alone, so store-router(V), survival, store-router(V)
counted the same pair twice and the recurrence bound (TOWN_CYCLE_BREAK_LIMIT)
zeroed the budget in one step.

Substrate: the input rows of the four recorded decisions 20633..20636 and their
recorded arbiter telemetry (tests/extract_entrance_travel_retired_fixture.py).
The process's early decisions were lost to log rotation, so no whole-lifetime
replay exists; these pins re-derive the arbiter's accounting from the recorded
boards and recorded reasons with the real ``_town_arbiter_progress_vector`` and
a real ``TownTurnArbiter``.  Each board is observed through the public
response path and ``prime`` (which builds the grid index a decision uses).
Walls, each declared:
- the policy is fresh, not the live process's policy (unavailable);
- DECLARED WALL: the travel producer's goal is the recorded descent target
  (31,150) (the capture's ``_descent_target_goal``).  The pins call the real
  travel producer ``_town_travel_key`` with that goal on the recorded board, so
  its travel state is the one it sets for that goal; they do not run the
  surrounding goal selection;
- the recorded 20634 decision is re-derived by the real town-kill producer on
  its recorded board;
- the recorded 20636 stop ('5', town:blocked:owner-retired) is observed with
  its recorded key and reason: it is the consequence under test, and E1 checks
  instead that the travel stays selectable on that board;
- E2's stall board is the recorded decision-20635 input with only the game
  turn advanced per repeat: the travel was posted and the player did not move.
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

from hengbot.cli import _consume_response_sequence
from hengbot.model import Position
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import ENTRANCE_TRAVEL_MACRO
from hengbot.policy_constants import TOWN_TRAVEL_STALL_LIMIT
from hengbot.town_arbiter import _new_town_turn_arbiter

from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "entrance-travel-retired-20260922.jsonl.gz"
FIXTURE_SHA256 = "7f3c944aceb5afaed1d0c0c8b37b036db139144a67d09a3aa2887f605db2b76e"
BOUNDARIES_SHA256 = "6cb56ffbf308c7264f5ea6782e62c93b973b62445138acc374f964044c37e5d3"
TRAVEL = "town:travel-entrance"
TELEMETRY = (
    "producer_owner", "progress", "budget_remaining_estimate",
    "would_retire", "retirement_set",
)


def _without_locomotion(vector):
    """The pre-fix view: the durable town vector without a registered walk."""
    if vector and isinstance(vector[-1], tuple) and vector[-1][:1] == ("locomotion",):
        return vector[:-1]
    return vector


class EntranceTravelRetiredRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        boundaries_path = FIXTURE.with_suffix(".boundaries.json")
        assert hashlib.sha256(boundaries_path.read_bytes()).hexdigest() == (
            BOUNDARIES_SHA256
        )
        cls.boundaries = json.loads(boundaries_path.read_text(encoding="utf-8"))
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.lines = list(stream)
        assert len(cls.lines) == sum(cls.boundaries["input_rows"])
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.goal = Position(*cls.boundaries["descent_target_goal"])

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.policy = _policy(self.directory, self.monrace)
        self.boards = []
        cursor = 0
        for count in self.boundaries["input_rows"]:
            segment = self.lines[cursor : cursor + count]
            cursor += count
            _decoded, snapshots = _consume_response_sequence(
                segment, self.policy, lambda _key: True, self.monrace,
                knowledge_ledger_path=self.directory / "knowledge.jsonl",
            )
            self.boards.append(snapshots[-1])

    def _produce(self, board, reason):
        """Run the recorded decision's producer on its board; return its key."""
        policy = self.policy
        policy.prime(board)
        if reason == TRAVEL:
            return policy._town_travel_key(
                board, self.goal, ENTRANCE_TRAVEL_MACRO, TRAVEL
            )
        if reason == "town:kill-mob-friendly":
            return policy._town_kill_mob_key(board)
        return self.boundaries["recorded"][3][0]

    def _observe(self, arbiter, board, key, reason, strip=False):
        policy = self.policy
        view = _without_locomotion if strip else (lambda vector: vector)
        policy.last_reason = reason
        telemetry = arbiter.observe(
            in_town=True,
            reason=reason,
            progress_vector=view(policy._town_arbiter_progress_vector(board, reason)),
            terminal=policy._town_arbiter_terminal_result(key),
            retirement_key_for=lambda owner: view(
                policy._town_retirement_clearance_key(board, owner, reason)
            ),
        )
        return {name: telemetry[name] for name in TELEMETRY}

    def _recorded_sequence(self, arbiter, strip=False, count=4):
        decided, telemetry = [], []
        for board, (_key, reason) in list(
            zip(self.boards, self.boundaries["recorded"])
        )[:count]:
            key = self._produce(board, reason)
            decided.append([key, reason])
            telemetry.append(self._observe(arbiter, board, key, reason, strip))
        return decided, telemetry

    def test_e0_recorded_boards_reproduce_recorded_decisions_and_accounting(self):
        # The producers re-derive every recorded key on its recorded board, and
        # without the walk's locomotion part the real arbiter reproduces the
        # recorded telemetry exactly: recurrence zeroes store-router at 20635.
        decided, telemetry = self._recorded_sequence(
            _new_town_turn_arbiter(), strip=True
        )
        self.assertEqual(decided, self.boundaries["recorded"])
        self.assertEqual(telemetry, self.boundaries["recorded_arbiter"])
        self.assertEqual(
            [[board.player.position.y, board.player.position.x]
             for board in self.boards],
            self.boundaries["recorded_positions"],
        )

    def test_e1_entrance_walk_closing_its_distance_is_not_retired(self):
        arbiter = _new_town_turn_arbiter()
        _decided, telemetry = self._recorded_sequence(arbiter)

        # Live 20635: (store-router, False, 0, would_retire, ['store-router']).
        self.assertEqual(telemetry[:3], [
            {"producer_owner": "store-router", "progress": True,
             "budget_remaining_estimate": TOWN_TRAVEL_STALL_LIMIT,
             "would_retire": False, "retirement_set": []},
            {"producer_owner": "survival", "progress": True,
             "budget_remaining_estimate": 8, "would_retire": False,
             "retirement_set": []},
            {"producer_owner": "store-router", "progress": True,
             "budget_remaining_estimate": TOWN_TRAVEL_STALL_LIMIT,
             "would_retire": False, "retirement_set": []},
        ])
        self.assertEqual(telemetry[3]["retirement_set"], [])

        # On the recorded 20636 board (33,134) the walk remains selectable:
        # the travel is re-issued instead of town:blocked:owner-retired.
        board = self.boards[3]
        self.assertEqual(self._produce(board, TRAVEL), ENTRANCE_TRAVEL_MACRO)
        self.assertTrue(arbiter.preview_may_select(
            TRAVEL, self.policy._town_arbiter_progress_vector(board, TRAVEL),
        ))
        # The registered distance is the remaining route to the entrance.
        self.assertEqual(
            [
                self.policy._town_arbiter_progress_vector(self.boards[index], TRAVEL)[-1][3:]
                for index in (0, 2, 3)
            ],
            [(self.goal, 32), (self.goal, 25), (self.goal, 16)],
        )

    def test_e2_entrance_walk_that_stops_closing_the_distance_is_retired(self):
        # Recorded 20633..20635, then the 20635 board again: the re-issued
        # travel did not move the player.
        arbiter = _new_town_turn_arbiter()
        self._recorded_sequence(arbiter, count=3)
        stall_board = self.boards[2]
        self.assertEqual(
            arbiter.registry["store-router"].budget, TOWN_TRAVEL_STALL_LIMIT
        )

        repeats = []
        for repeat in range(1, 3 * TOWN_TRAVEL_STALL_LIMIT):
            board = replace(stall_board, turn=stall_board.turn + 10 * repeat)
            key = self._produce(board, TRAVEL)
            telemetry = self._observe(arbiter, board, key, TRAVEL)
            repeats.append((key, telemetry["budget_remaining_estimate"],
                            telemetry["would_retire"]))
            if telemetry["would_retire"]:
                break

        # The travel is posted but the player stays at (38,126): every repeat
        # is non-progress and the owner retires on the existing bound, while
        # the producer would still re-issue the travel.
        self.assertEqual(repeats, [
            (ENTRANCE_TRAVEL_MACRO, TOWN_TRAVEL_STALL_LIMIT - count,
             count == TOWN_TRAVEL_STALL_LIMIT)
            for count in range(1, TOWN_TRAVEL_STALL_LIMIT + 1)
        ])
        self.assertFalse(arbiter.preview_may_select(
            TRAVEL, self.policy._town_arbiter_progress_vector(stall_board, TRAVEL),
        ))


if __name__ == "__main__":
    unittest.main()
