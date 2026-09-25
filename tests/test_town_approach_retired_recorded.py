"""Recorded pin: a town approach whose claimed distance falls is not retired.

Live incident 2026-09-25 06:15:50-06:23:14 (one bot process, 2,052 logged
decisions, resumed onto the running game): back in the Outpost after a
guardian-kit-insufficient return from the Orc cave, a town fight interrupted
native travel to the Black Market (store 7).  ``shop:approach`` then walked
single steps ('9', '6') toward the entrance at (45, 123).  The S2a.1 claim
ledger shows one Reach claim (claim 925) whose distance fell on every
decision, 33 -> 20, yet the arbiter scored ``progress: False`` on 11 of those
14 decisions, spent the store-router budget 8 -> 0, retired the owner on
sequence 2046 and the next decision stopped the run with
``town:blocked:owner-retired``.

Root cause: the arbiter's locomotion part measured the walk with the
Manhattan sum |dy| + |dx|.  Above the goal's row a '9' step closes |dx| and
opens |dy|, so the sum stayed flat (32, 32, 32 ...) on every such step while
the eight-way step distance the policy and the claim ledger use
(``Position.distance_to``) fell by one.  The same flat sum also made the
first walk board (sequence 2032, (47, 89)) repeat the vector of sequence 2024
((46, 88), both 36) and retire the owner at once by recurrence.  User
decision 2026-09-23 (ownership contract): progress is distance plus the
expected observation, and a strictly falling distance to the claimed goal is
progress.

Substrate: every recorded decision of the process, replayed through the
public response path on one policy (tests/extract_town_approach_retired_
fixture.py; the calibration file is the one the process loaded).
Walls, each declared:
- the recorded periodic save/dump decisions receive the CLI timer request
  that produced them;
- Home history/disposal files and the calibration file live in a temporary
  directory;
- DECLARED WALL (executor binding): from decision 2027 on, the board of every
  decision that follows a posted key carries the live input executor's
  ``_completed_operation_sequence``/``_owner`` (the previous decision's
  sequence and reason).  The executor adds them to the board it composes
  after an accepted operation and the state log never carries them; without
  them decision 2027 cannot see that the town fight interrupted the native
  travel of 2026 (``store:entry-interrupted-replan`` recorded).  With the
  binding the pre-fix code reproduces all 2,052 recorded decisions, the
  stop included.
- DECLARED WALL (live replay only, orc-cave-residual-path): the live town
  router had no guardian-landing gate, so the replay answers
  ``_recall_landing_guardian_blocked`` with False; otherwise the 06:22:31
  recall to the Orc cave (B below) would be refused and every later recorded
  board, the walk included, would be counterfactual.  B1 decides the 06:22:31
  board without it.
No wall touches the approach producer, the progress vector or the arbiter.

B (orc-cave-residual-path, same capture): 06:22:31 ``town:recall-to-alt-
dungeon`` 'rhc' read Word of Recall to the Orc cave (target 3, no alternate,
streak 0), whose landing 23 is its guardian floor; at 06:22:50 the dive came
straight back (``guardian-kit-insufficient``).  The target came from the
conquest latch (``_conquest_target`` / ``_conquest_committed``), committed at
sequence 1890 on a mid-transaction kit that could beat the guardian and kept
after the kit changed (B1 path test).  The town router now refuses a recall
whose landing is a guardian floor the current kit cannot pass
(``_guardian_floor_blocked``) and switches like the guardian valve.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import copy
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import SHOP_APPROACH_STUCK_LIMIT, TOWN_TRAVEL_STALL_LIMIT

from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "town-approach-retired-20260925.jsonl.gz"
CALIBRATION = FIXTURES / (
    "guardian-recall-pingpong-20260925.character-calibration.json"
)
FIXTURE_SHA256 = "249feeff221d652c51bb8b56d9c4ec021ce17bd309f39b17d9d53f940e106093"
BOUNDARIES_SHA256 = (
    "9706267ad37124770d48b06af6281f8876aed2c3244b66680d0b1de63ea88a20"
)
CALIBRATION_SHA256 = (
    "a90e4700854b1b3cf839a278a846078c7f9d768c82c058551c6f52173660016b"
)
BINDING_FROM = 2027  # store:entry-interrupted-replan, the first bound board
WALK_START = 2036  # sequence 2032: the first shop:approach step after the fight
WALK_END = 2050  # sequence 2046: the live retirement
STOP = 2051  # sequence 2047: town:blocked:owner-retired
STORE_7_ENTRANCE = [45, 123]
# B (orc-cave-residual-path): the Orc cave path, by log index.
ORC_CAVE = 3
FOREST = 7
ORC_CAVE_LANDING = 23  # recorded dungeon_recall_depths[3]; its guardian floor
LATCH = 1893  # sequence 1890, 06:21:37: _conquest_target commits the Orc cave
KIT_CHANGED = 1899  # sequence 1896: the shield is on, the guardian unbeatable
RECALL = 1966  # sequence 1963, 06:22:31: 'rhc' town:recall-to-alt-dungeon
BOUNCE = 1991  # sequence 1988, 06:22:50: 'rh' return:recall from (3, 23)
PATH = (LATCH - 1, LATCH, KIT_CHANGED - 1, KIT_CHANGED, RECALL, BOUNCE)


class TownApproachRetiredRecordedTest(unittest.TestCase):
    replay = None
    path = None
    fixed_recall = None

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
        boundaries = json.loads(boundaries_path.read_text(encoding="utf-8"))
        fields = boundaries["recorded_fields"]
        cls.recorded = [dict(zip(fields, row)) for row in boundaries["recorded"]]
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.lines = list(stream)
        assert len(cls.lines) == sum(boundaries["input_rows"])
        assert len(cls.recorded) == STOP + 1
        cls.starts = [0]
        for count in boundaries["input_rows"]:
            cls.starts.append(cls.starts[-1] + count)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    @classmethod
    def _new_policy(cls, directory: Path):
        policy = _policy(directory, cls.monrace)
        policy._character_calibration_path.write_bytes(CALIBRATION.read_bytes())
        return policy

    @classmethod
    def _board_lines(cls, index):
        segment = cls.lines[cls.starts[index] : cls.starts[index + 1]]
        previous = cls.recorded[index - 1] if index else None
        if index >= BINDING_FROM and previous["key"]:
            # DECLARED WALL (executor binding): see the module docstring.
            row = json.loads(segment[-1])
            row["_completed_operation_sequence"] = previous["decision_sequence"]
            row["_completed_operation_owner"] = previous["reason"]
            segment = segment[:-1] + [json.dumps(row, ensure_ascii=False) + "\n"]
        return segment

    @classmethod
    def _consume(cls, policy, index, directory):
        _decoded, snapshots = _consume_response_sequence(
            cls._board_lines(index), policy, lambda _key: True, cls.monrace,
            knowledge_ledger_path=directory / "knowledge.jsonl",
        )
        recorded_reason = cls.recorded[index]["reason"]
        if recorded_reason == "periodic:game-save":
            policy.request_game_save()
        elif recorded_reason == "periodic:character-dump":
            policy.request_character_dump()
        return snapshots[-1]

    @staticmethod
    def _decide(policy, snapshot, *, live_gate=True):
        if live_gate:
            # DECLARED WALL (live replay): see the module docstring.
            with patch.object(
                policy, "_recall_landing_guardian_blocked", return_value=False,
                create=True,  # pre-fix code has no gate: fail by assertion
            ):
                key = policy.choose_key(snapshot)
        else:
            key = policy.choose_key(snapshot)
        telemetry = policy._town_turn_arbiter.telemetry or {}
        claim = policy.decision_claim or {}
        decided = {
            "key": str(key),
            "reason": policy.last_reason,
            "producer_owner": telemetry.get("producer_owner"),
            "progress": telemetry.get("progress"),
            "budget_remaining_estimate": telemetry.get(
                "budget_remaining_estimate"
            ),
            "retirement_set": telemetry.get("retirement_set"),
            "claim_id": claim.get("claim_id"),
            "claim_state": claim.get("state"),
            "claim_distance": claim.get("distance"),
            # S2b.1: a preempted claim resumed under its own id on this row
            "claim_resumed": bool(claim.get("resumed")),
        }
        policy.confirm_key_posted(key)
        return decided

    @classmethod
    def _replay(cls):
        """Replay the whole recorded process on one policy."""
        if cls.replay is not None:
            return cls.replay
        cls.path = {}
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            policy = cls._new_policy(directory)
            replay = []
            for index in range(STOP + 1):
                snapshot = cls._consume(policy, index, directory)
                if index == RECALL:
                    # B1: the fixed town router on the live state and board
                    # of the 06:22:31 recall, deciding twice on that board.
                    fixed = copy.deepcopy(policy)
                    cls.fixed_recall = []
                    for _decision in range(2):
                        row = cls._decide(fixed, snapshot, live_gate=False)
                        row.update(
                            alternate=fixed._alternate_dungeon,
                            target=fixed._target_dungeon_id,
                            conquest=fixed._conquest_committed,
                            forest_selection=fixed._recall_selection_key(
                                snapshot, FOREST
                            ),
                        )
                        cls.fixed_recall.append(row)
                replay.append(cls._decide(policy, snapshot))
                if index in PATH:
                    cls.path[index] = (
                        policy._conquest_committed,
                        policy._target_dungeon_id,
                        policy._alternate_dungeon,
                        policy._guardian_floor_blocked(
                            snapshot, ORC_CAVE,
                            snapshot.dungeon_recall_depths[ORC_CAVE],
                        ),
                        (snapshot.floor_key[0], snapshot.floor_key[1]),
                    )
            cls.replay = replay
        return cls.replay

    # ------------------------------------------------------------ recorded
    def test_recorded_walk_closes_its_claimed_distance_and_is_retired(self):
        walk = self.recorded[WALK_START : WALK_END + 1]
        self.assertEqual(
            [row["decision_sequence"] for row in walk], list(range(2032, 2047))
        )
        self.assertEqual({row["reason"] for row in walk}, {"shop:approach"})
        self.assertEqual({row["key"] for row in walk}, {"9", "6"})
        self.assertEqual(
            {tuple(row["claim_goal"]) for row in walk}, {tuple(STORE_7_ENTRANCE)}
        )
        # The first board's claim (924) was retired with the owner; one claim
        # (925) holds the rest of the walk.  Its distance falls on every
        # decision.
        self.assertEqual(walk[0]["claim_id"], 924)
        self.assertEqual({row["claim_id"] for row in walk[1:]}, {925})
        self.assertEqual(
            [row["claim_distance"] for row in walk], list(range(34, 19, -1))
        )
        self.assertEqual(
            [row["progress"] for row in walk[1:]].count(False), 11
        )
        self.assertEqual(
            [row["budget_remaining_estimate"] for row in walk],
            [0, 8, 8, 7, 6, 5, 8, 7, 6, 5, 4, 3, 2, 1, 0],
        )
        self.assertIn("store-router", walk[0]["retirement_set"])
        self.assertIn("store-router", walk[-1]["retirement_set"])
        stop = self.recorded[STOP]
        self.assertEqual(
            (stop["key"], stop["reason"]), ("5", "town:blocked:owner-retired")
        )
        self.assertEqual(
            min(TOWN_TRAVEL_STALL_LIMIT, SHOP_APPROACH_STUCK_LIMIT), 8
        )

    # ------------------------------------------------------------ A1
    def test_replay_reproduces_every_recorded_decision_before_the_stop(self):
        replay = self._replay()
        self.assertEqual(
            [
                index
                for index in range(STOP + 1)
                if (replay[index]["key"], replay[index]["reason"])
                != (self.recorded[index]["key"], self.recorded[index]["reason"])
            ],
            [STOP],
        )

    def test_a1_walk_whose_claimed_distance_falls_is_not_retired(self):
        replay = self._replay()
        walk = replay[WALK_START : STOP + 1]
        # The recorded walk is decided step for step ...
        self.assertEqual(
            [(row["key"], row["reason"]) for row in walk[:-1]],
            [
                (row["key"], row["reason"])
                for row in self.recorded[WALK_START : WALK_END + 1]
            ],
        )
        # ... under ONE claim, never retired, whose distance falls on every
        # decision.  Live retired the walk's first claim (924) on its first
        # board by recurrence and opened 925 for the rest.  S2b.1 (design rev
        # 10.1 item 5): this walk to the same entrance was opened seven
        # decisions earlier as claim 903, suspended when melee took the
        # decision (the town kill and a loot pickup nested above it), and it
        # resumes here under its own id -- where live, before the ladder,
        # opened 924.
        self.assertTrue(walk[0]["claim_resumed"])
        self.assertEqual(
            {(row["claim_id"], row["claim_state"]) for row in walk},
            {(903, "active")},
        )
        self.assertEqual(
            [row["claim_distance"] for row in walk], list(range(34, 18, -1))
        )
        # and every step is progress: the owner keeps its whole budget and is
        # never retired.  Live 2046 retired it and 2047 stopped the run.
        self.assertEqual(
            {
                (
                    row["producer_owner"], row["progress"],
                    row["budget_remaining_estimate"],
                )
                for row in walk
            },
            {("store-router", True, 8)},
        )
        self.assertEqual({tuple(row["retirement_set"]) for row in walk}, {()})
        # The recorded stop board is one more step of the same walk.
        self.assertEqual(walk[-1]["reason"], "shop:approach")
        self.assertIn(walk[-1]["key"], set("12346789"))

    # ------------------------------------------------------------ B
    def test_recorded_recall_onto_the_orc_cave_guardian_floor(self):
        recorded = self.recorded
        # Angband is the target (no alternate) until the conquest latch.
        self.assertEqual(
            {
                (row["target_dungeon_id"], row["alternate_dungeon_id"])
                for row in recorded[:LATCH]
            },
            {(1, None)},
        )
        self.assertEqual(
            {
                (row["target_dungeon_id"], row["alternate_dungeon_id"])
                for row in recorded[LATCH:RECALL + 1]
            },
            {(ORC_CAVE, None)},
        )
        row = recorded[RECALL]
        self.assertEqual(
            (row["decision_sequence"], row["key"], row["reason"],
             row["over_extended_dive_streak"]),
            (1963, "rhc", "town:recall-to-alt-dungeon", 0),
        )
        row = recorded[BOUNCE]
        self.assertEqual(
            (row["key"], row["reason"], row["dungeon_id"], row["level"],
             row["last_return_trigger"]),
            ("rh", "return:recall", ORC_CAVE, ORC_CAVE_LANDING,
             "guardian-kit-insufficient"),
        )

    def test_b1_path_is_the_conquest_latch_held_after_the_kit_changed(self):
        """The path that made the Orc cave the recall target, on the replay.

        The recorded ``over_extension`` rows show the target turning to 3
        with no alternate at sequence 1890 -- neither the picker nor the
        unsafe-recall fallback (both set an alternate).  On the replay
        (which reproduces every recorded decision) that is
        ``_conquest_target``: mid equipment transaction the two-handed
        scythe had no shield beside it and the Orc cave guardian projected
        as beatable, so the latch committed 3.  Six decisions later the
        shield was worn, the guardian floor became blocked, and the latch --
        which by design breaks only on structural change -- kept the target
        through the 06:22:31 recall and the bounce.
        """
        self._replay()
        self.assertEqual(
            self.path,
            {
                LATCH - 1: (None, 1, None, True, (0, 0)),
                LATCH: (ORC_CAVE, ORC_CAVE, None, False, (0, 0)),
                KIT_CHANGED - 1: (ORC_CAVE, ORC_CAVE, None, False, (0, 0)),
                KIT_CHANGED: (ORC_CAVE, ORC_CAVE, None, True, (0, 0)),
                RECALL: (ORC_CAVE, ORC_CAVE, None, True, (0, 0)),
                BOUNCE: (ORC_CAVE, ORC_CAVE, None, True, (ORC_CAVE, ORC_CAVE_LANDING)),
            },
        )

    def test_b1_the_0622_decision_no_longer_recalls_to_the_orc_cave(self):
        """User decisions 2026-09-25 (guardian-recall-pingpong r2/r3).

        On the live state and the recorded board of the 06:22:31 recall the
        fixed town router refuses the landing on the blocked guardian floor
        and switches as the guardian valve does: the shallowest landing that
        is not a blocked guardian floor, deeper allowed -- Forest (24).  The
        same board then recalls to Forest instead of the Orc cave.
        """
        self._replay()
        switch, recall = self.fixed_recall
        # The recorded board stands on the Black Market entrance (the
        # 06:22:30 observe-and-leave), so the switch's WAIT is emitted as the
        # existing entrance step-off wrapper.
        self.assertEqual(
            switch["reason"],
            "town:entrance-step-off:town:unsafe-recall-fallback",
            self.fixed_recall,
        )
        self.assertIn(switch["key"], set("12346789"))
        self.assertEqual(
            (switch["alternate"], switch["target"], switch["conquest"]),
            (FOREST, FOREST, None),
        )
        self.assertEqual(recall["reason"], "town:recall-to-alt-dungeon")
        self.assertEqual(recall["key"], "rh" + recall["forest_selection"])
        self.assertNotEqual(recall["key"], self.recorded[RECALL]["key"])


if __name__ == "__main__":
    unittest.main()
