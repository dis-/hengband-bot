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
The speed-adjusted optimizer changes the key at sequence 242. Later boards
are counterfactual new-code measurements; the late walk is now store-router
owned, while the live-key comparison ends before 242.

R4 boundary (USER DECISION 2026-10-01: the strip calibration is replaced by
the equipped C-sheet read): sequence 210 is the first recorded decision of
the removed strip phases.  The base code armed the strip deposit phase on that
decision (its Home trip ``shop:travel``); 211-215 deposit the whole pack,
216-227 take every worn item off (the 537 -> 506 max-HP clamp at 218 is that
takeoff), 229 is the naked capture and 244-248 restore the supplies.  The
replay ends before 210.  The late walk pins (former m1/m2, sequences 699-708)
are therefore unreachable here; see CALIBRATION-OBSOLETE-PINS.md for where
that protection lives now and what was lost.
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

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import TOWN_TRAVEL_STALL_LIMIT

from recorded_emergency_loot_gate import pre_progressing_loot_gate_replay
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "morivant-travel-retired-20260922.jsonl.gz"
FIXTURE_SHA256 = "285b1b312642a9b004759fb209538efc8f9b95dbc3a9b5abccac9f030a3ff28a"
BOUNDARIES_SHA256 = "0858a57d73d6933db11b817cdec96fbe858ab73ae5a3ea0575e8b7138702f62a"
CALIBRATION = FIXTURES / "esp-threat-rest-20260921.character-calibration.json"
CALIBRATION_SHA256 = "d470a028bdf04cfe5847fa11f28c2f17eafcbe92a07b4314eaf62dadd286edf7"
WALK_START = 699
TERMINAL = 708
STALL_AFTER = 703
# First recorded decision of the removed strip calibration (see docstring).
STRIP_BOUNDARY = 210


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
    @pre_progressing_loot_gate_replay  # declared wall: pre-6c0910fb loot gate (tests/recorded_emergency_loot_gate.py)
    def _replay(cls):
        """Replay the recorded lifetime and decide the recorded terminal input."""
        if cls.replay is not None:
            return cls.replay
        policy = _policy(cls.directory, cls.monrace)
        decided = {}
        progress = {}
        stall = None
        for sequence in range(1, STRIP_BOUNDARY):
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

    def test_m0_replay_matches_recorded_lifetime_before_the_strip_calibration(self):
        decided, _progress, _stall = self._replay()
        recorded = self.boundaries["recorded"]
        # R4 (USER DECISION 2026-10-01): compare every recorded decision
        # before the first strip-calibration decision (sequence 210) and end
        # the replay there.
        self.assertEqual(sorted(decided), list(range(1, STRIP_BOUNDARY)))
        divergent = [
            sequence for sequence in range(1, STRIP_BOUNDARY)
            if decided[sequence] != recorded[sequence - 1]
        ]
        # melee-threat-p95-adjacency (user 2026-09-22) moved exactly these
        # earlier combat decisions:
        # 153 emergency:teleport -> melee (HP 370, operational 554 -> 316),
        # 155 return:recall -> rest (follows 153: no teleport was read),
        # 158 emergency:teleport -> melee (HP 341, 372 -> 210).
        # USER DECISION 2026-10-03 06:0x (heal-vs-teleport; next turn = the
        # one-turn p95, clarified 08:5x) moved:
        # 170 emergency:teleport -> item:heal (HP 145 < 268.5 among 16 fire
        # trolls: the lethal ladder, next turn 239 <= Healing 300).
        self.assertEqual(divergent, [153, 155, 158, 170])
        self.assertEqual(decided[170][1], "item:heal")
        # The recorded boundary is the strip session: Home trip, deposit of
        # the whole pack, takeoff of every worn item, naked capture.
        self.assertEqual(recorded[STRIP_BOUNDARY - 1], ["\x1b`n(.", "shop:travel"])
        self.assertEqual(
            [row[1] for row in recorded[STRIP_BOUNDARY:STRIP_BOUNDARY + 5]],
            ["home:store-context-exit"] + ["home:atomic-deposit"] * 4,
        )
        self.assertEqual(
            {row[1] for row in recorded[215:227]} - {"town:seek-shelter"},
            {"equipment-transaction:takeoff"},
        )
        self.assertEqual(recorded[228], ["Cf\ry\x1b\x1b", "calibration:request-naked-character"])


if __name__ == "__main__":
    unittest.main()
