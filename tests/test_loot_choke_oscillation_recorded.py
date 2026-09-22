"""Pins: the anticipatory retreat owns its route (loot/choke alternation).

Live incident: Orc cave floor (3, 21, 0), 2026-09-23 06:00:14-06:00:18,
protocol 3, decisions 10913-10936 of one bot process.  Nine ESP-perceived
monsters stood west of the player and one item lay two cells away.  At (3, 99)
two of them were within the convergence window, so `detected:prepare-choke`
posted '6'; its own step put them one cell further out, so at (3, 100) the same
owner fell silent and `seek-loot` posted '4' back into the window.  The two
owners undid each other one cell apart until the loop detector stopped the bot
at turn 4828473.  The visible-monster choke engagement of the same floor was
already `phase: release`, `release_cause: low-threat` in every frozen decision,
and no hostile was visible: nothing was going to end the alternation.

The fix is ownership, not another gate: a started retreat commits to the covered
cell it chose and keeps the decision until the player reaches it (the bounded
`summoner:hold-choke` then owns the wait) or the pack, the floor, a visible
hostile or the 50-turn bound retires it.  The 10%/50% damage bounds and the
50-turn sight rule are untouched.

Substrate: tests/fixtures/loot-choke-oscillation-20260923.jsonl.gz, frozen by
tests/extract_loot_choke_oscillation_fixture.py at decision boundaries taken
from `timing.jsonl_drain_records` (see the .provenance.txt beside it; the
retained ring begins mid-member, so the bytes before the first gzip magic are
dropped and the remainder decompresses whole).  The fixture carries the recorded
decision record and the input board of each of the 24 decisions, plus the
recorded `~f` skill list of the same character and run (protocol-3 boards carry
no two-weapon/shield skill_exp and the live process had read its list long
before this window).

Replay fidelity: a restarted policy fed the frozen boards reproduces the
recorded (key, reason) of decisions 10915-10936 before the fix, and the recorded
key of 10913-10914 with its own reason (a restart has not yet recorded the
floor's known loot).  Test 2 pins the first alternation decision as reproduced
and the recorded reversal as no longer taken.

Walls: tests/__init__ runtime-file isolation only; the boards are dungeon
floors, so no Home/town/shop producer with a file of its own is reached.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import SUMMONER_CHOKE_NEIGHBORS


FIXTURE = (
    Path(__file__).parent / "fixtures" / "loot-choke-oscillation-20260923.jsonl.gz"
)
FIXTURE_SHA256 = "a6195e5ed8f0c5d947b34f07d287fde139e0fd569ca98950af53ae74e1586442"
MONRACES = Path(r"C:\hengband\lib\edit\MonraceDefinitions.jsonc")
CHOKE = Position(3, 99)  # the cell where the pack entered the convergence window
OPEN = Position(3, 100)  # the cell the retreat's own step reached
ALTERNATION = 10919  # first decision of the uninterrupted recorded alternation
LAST = 10936  # the decision the loop detector stopped on


class LootChokeOscillationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            records = [json.loads(line) for line in stream]
        cls.capture = next(r for r in records if r["role"] == "capture")
        cls.skill = next(r for r in records if r["role"] == "skill-knowledge")["board"]
        cls.inputs = [r for r in records if r["role"] == "decision-input"]
        cls.monrace = load_monrace_knowledge(MONRACES)

    def _replay(self, *, strip_detected=False):
        policy = HengbotPolicy(monrace_knowledge=self.monrace)
        # The live process read its ~f list long before this window; a restart
        # consumes the recorded response through the same public entry point
        # the client uses, so no board here opens on the request.
        policy.consume_skill_knowledge(self.skill)
        replay = []
        for record in self.inputs:
            snapshot = parse_snapshot(record["board"], self.monrace)
            if strip_detected:
                snapshot = replace(snapshot, detected_monsters=[])
            key = policy.choose_key(snapshot)
            replay.append((record["decision"], snapshot, str(key), policy.last_reason))
            policy.confirm_key_posted(key)
        return policy, replay

    @staticmethod
    def _posted_target(policy, snapshot, key):
        origin = snapshot.player.position
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                candidate = Position(origin.y + dy, origin.x + dx)
                if candidate != origin and policy._step_toward(
                    snapshot, candidate
                ) == key:
                    return candidate
        raise AssertionError(f"{key!r} is not a step from {origin}")

    def test_fixture_freezes_the_recorded_alternation(self):
        recorded = [
            (
                row["decision_sequence"],
                Position(row["position"]["y"], row["position"]["x"]),
                row["key"],
                row["reason"],
            )
            for row in (record["decision"] for record in self.inputs)
        ]
        self.assertEqual(
            [sequence for sequence, *_rest in recorded],
            list(range(LAST - len(self.inputs) + 1, LAST + 1)),
        )
        window = [row for row in recorded if row[0] >= ALTERNATION]
        self.assertEqual(
            [row[1:] for row in window],
            [(CHOKE, "6", "detected:prepare-choke"), (OPEN, "4", "seek-loot")] * 9,
        )
        stop = self.capture["stop"]
        self.assertEqual(stop["kind"], "loop-detected")
        self.assertEqual(tuple(stop["position"]), (OPEN.y, OPEN.x))
        self.assertEqual(
            set(stop["last_reasons"]), {"seek-loot", "melee", "detected:prepare-choke"}
        )
        for record in self.inputs:
            with self.subTest(sequence=record["decision"]["decision_sequence"]):
                engagement = record["decision"]["choke_engagement"]
                self.assertEqual(engagement["phase"], "release")
                self.assertEqual(engagement["release_cause"], "low-threat")
                self.assertEqual(record["decision"]["loot"]["target"],
                                 {"y": 5, "x": 97})
        self.assertEqual(
            {record["decision"]["visible_hostiles"] for record in self.inputs},
            {0, 1},  # one recorded melee decision saw a hostile
        )

    def test_replay_keeps_one_owner_instead_of_the_recorded_reversal(self):
        policy, replay = self._replay()
        window = [row for row in replay if row[0]["decision_sequence"] >= ALTERNATION]

        first = window[0]
        self.assertEqual(
            (first[1].player.position, first[2], first[3]),
            (CHOKE, first[0]["key"], first[0]["reason"]),
        )
        self.assertEqual(first[3], "detected:prepare-choke")
        self.assertEqual(
            {reason for _decision, _snapshot, _key, reason in window},
            {"detected:prepare-choke"},
        )
        self.assertNotIn(
            "seek-loot", {reason for _decision, _snapshot, _key, reason in window}
        )
        reversed_decisions = [
            decision["decision_sequence"]
            for decision, snapshot, key, _reason in window
            if snapshot.player.position == OPEN
            and (key, decision["key"], decision["reason"])
            == ("4", "4", "seek-loot")
        ]
        self.assertEqual(reversed_decisions, [])
        self.assertIsNotNone(policy._detected_threat_route)

    def test_replayed_owner_commits_to_one_covered_cell_and_closes_on_it(self):
        policy, replay = self._replay()
        window = [row for row in replay if row[0]["decision_sequence"] >= ALTERNATION]
        destinations = set()

        for _decision, snapshot, key, _reason in window:
            route = policy._detected_threat_route
            self.assertIsNotNone(route)
            self.assertEqual(route[0], snapshot.floor_key)
            self.assertTrue(route[2])
            destinations.add(route[1])
            target = self._posted_target(policy, snapshot, key)
            self.assertLess(
                target.distance_to(route[1]),
                snapshot.player.position.distance_to(route[1]),
            )

        self.assertEqual(len(destinations), 1)
        destination = destinations.pop()
        board = window[-1][1]
        self.assertLessEqual(
            policy._open_neighbor_count(board, destination),
            SUMMONER_CHOKE_NEIGHBORS - 1,
        )
        self.assertIsNotNone(policy._position_target_step(board, destination))

    def test_loot_still_owns_the_recorded_board_without_a_perceived_pack(self):
        _policy, replay = self._replay(strip_detected=True)
        decision, snapshot, key, reason = replay[-1]

        self.assertEqual(decision["decision_sequence"], LAST)
        self.assertEqual(snapshot.player.position, OPEN)
        self.assertEqual((key, reason), (decision["key"], decision["reason"]))
        self.assertEqual((key, reason), ("4", "seek-loot"))


if __name__ == "__main__":
    unittest.main()
