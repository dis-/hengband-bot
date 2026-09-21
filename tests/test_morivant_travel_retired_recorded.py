"""Recorded pins: the Morivant *Identify* walk is locomotion, not wandering.

Live incident 2026-09-22 03:11:43-03:15:09 (one bot process, 708 decisions):
back in the Outpost after an emergency recall, the *Identify* expedition for
two carried boots walked toward the Inn (town teleport to Morivant).  Every
step moved one cell closer along the route, yet the cross-town owner
registered no goal, the arbiter saw an unchanged durable vector, retired the
owner after TOWN_TRAVEL_STALL_LIMIT steps and the bot stopped on
``town:blocked:owner-retired``.

Substrate: every recorded decision of the process lifetime, replayed through
the public response path on one policy (tests/extract_morivant_travel_
retired_fixture.py).  Decisions 1..708 reproduce the recorded (key, reason)
exactly on the pre-fix code.
Walls, each on a collaborator that is not under test:
- the recorded periodic save/dump decisions receive the CLI timer request
  that produced them;
- Home history/disposal files and the calibration file live in a temporary
  directory (the calibration file is the last preserved pre-run copy; see the
  fixture provenance).
- M2's stall board is the recorded decision-703 input with only the game turn
  advanced per repeat: the step was posted and the player did not move.
No wall touches the Morivant producer, the progress core or the arbiter.
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import TOWN_TRAVEL_STALL_LIMIT

from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "morivant-travel-retired-20260922.jsonl.gz"
FIXTURE_SHA256 = "285b1b312642a9b004759fb209538efc8f9b95dbc3a9b5abccac9f030a3ff28a"
BOUNDARIES_SHA256 = "0858a57d73d6933db11b817cdec96fbe858ab73ae5a3ea0575e8b7138702f62a"
CALIBRATION = FIXTURES / "esp-threat-rest-20260921.character-calibration.json"
CALIBRATION_SHA256 = "d470a028bdf04cfe5847fa11f28c2f17eafcbe92a07b4314eaf62dadd286edf7"
TRAVEL = "town:morivant-full-identify:travel-2"
WALK_START = 699
TERMINAL = 708
STALL_AFTER = 703


class MorivantTravelRetiredRecordedTest(unittest.TestCase):
    replay = None

    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        boundaries_path = FIXTURE.with_suffix(".boundaries.json")
        assert hashlib.sha256(boundaries_path.read_bytes()).hexdigest() == (
            BOUNDARIES_SHA256
        )
        assert hashlib.sha256(CALIBRATION.read_bytes()).hexdigest() == (
            CALIBRATION_SHA256
        )
        cls.boundaries = json.loads(boundaries_path.read_text(encoding="utf-8"))
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.lines = list(stream)
        assert len(cls.lines) == sum(cls.boundaries["input_rows"])
        cls.starts = [0]
        for count in cls.boundaries["input_rows"]:
            cls.starts.append(cls.starts[-1] + count)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        directory = TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        cls.directory = Path(directory.name)

    @classmethod
    def _consume(cls, policy, sequence):
        segment = cls.lines[cls.starts[sequence - 1] : cls.starts[sequence]]
        _decoded, snapshots = _consume_response_sequence(
            segment, policy, lambda _key: True, cls.monrace,
            knowledge_ledger_path=cls.directory / "knowledge.jsonl",
        )
        return snapshots[-1]

    @classmethod
    def _replay(cls):
        """Replay the recorded lifetime and decide the recorded terminal input."""
        if cls.replay is not None:
            return cls.replay
        policy = _policy(cls.directory, cls.monrace)
        decided = {}
        progress = {}
        stall = None
        for sequence in range(1, TERMINAL + 1):
            snapshot = cls._consume(policy, sequence)
            recorded_reason = cls.boundaries["recorded"][sequence - 1][1]
            if recorded_reason == "periodic:game-save":
                policy.request_game_save()
            elif recorded_reason == "periodic:character-dump":
                policy.request_character_dump()
            key = policy.choose_key(snapshot)
            decided[sequence] = [str(key), policy.last_reason]
            telemetry = policy._town_turn_arbiter.telemetry or {}
            progress[sequence] = (
                telemetry.get("producer_owner"), telemetry.get("progress"),
                tuple(telemetry.get("retirement_set", ())),
            )
            policy.confirm_key_posted(key)
            if sequence == STALL_AFTER:
                stall = (copy.deepcopy(policy), snapshot)
        cls.replay = decided, progress, stall
        return cls.replay

    def test_m0_replay_matches_recorded_lifetime_before_the_terminal(self):
        decided, _progress, _stall = self._replay()
        recorded = self.boundaries["recorded"]
        divergent = [
            sequence for sequence in range(1, TERMINAL)
            if decided[sequence] != recorded[sequence - 1]
        ]
        self.assertEqual(divergent, [])
        self.assertEqual(recorded[TERMINAL - 1], ["5", "town:blocked:owner-retired"])

    def test_m1_recorded_walk_closing_its_distance_is_not_retired(self):
        decided, progress, _stall = self._replay()

        # Live 708: ('5', 'town:blocked:owner-retired') with cross-town
        # retired after 700..707 were counted as no-progress.
        self.assertEqual(decided[TERMINAL], ["6", TRAVEL])
        self.assertEqual(
            [progress[sequence] for sequence in range(WALK_START, TERMINAL + 1)],
            [("cross-town", True, ())] * (TERMINAL - WALK_START + 1),
        )
        self.assertEqual(
            [
                self.boundaries["recorded_positions"][sequence - 1]
                for sequence in range(WALK_START, TERMINAL + 1)
            ],
            [
                [45, 84], [46, 85], [46, 86], [46, 87], [46, 88],
                [46, 89], [45, 90], [44, 91], [43, 92], [42, 93],
            ],
        )

    def test_m2_walk_that_stops_closing_the_distance_is_still_retired(self):
        _decided, _progress, (policy, snapshot) = self._replay()
        policy = copy.deepcopy(policy)
        self.assertEqual(
            policy._town_turn_arbiter.registry["cross-town"].budget,
            TOWN_TRAVEL_STALL_LIMIT,
        )

        stalled = []
        for repeat in range(1, 3 * TOWN_TRAVEL_STALL_LIMIT):
            board = replace(snapshot, turn=snapshot.turn + 10 * repeat)
            key = policy.choose_key(board)
            stalled.append((str(key), policy.last_reason))
            policy.confirm_key_posted(key)
            if policy.last_reason == "town:blocked:owner-retired":
                break

        # The step toward (46,89) is posted but the player stays at (46,88):
        # the distance stops closing, each repeat is non-progress, and the
        # owner retires on the existing bound counted from the stall onset.
        self.assertEqual(
            stalled,
            [("6", TRAVEL)] * TOWN_TRAVEL_STALL_LIMIT
            + [("5", "town:blocked:owner-retired")],
        )


if __name__ == "__main__":
    unittest.main()
