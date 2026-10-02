"""Recorded pin: the Q2 travel walk to the Outpost inn is progress.

Live stops 2026-10-02 13:40:31, 13:41:22 and 13:41:52
(``town:blocked:owner-retired``, identical tails; commit 04550251,
``--enforce-crossarea-fundraising``, S3.3 switch off).  The 13:41:27
process of the 13:41:52 stop is frozen by
tests/extract_q2travel_progress_fixture.py:

- 2..5: ``fixedquest:q2-travel`` (owner quest-request).  The fixed-quest
  head is Q2 (untaken, town 1 = Telmora); the player is in town 0 (the
  Outpost), so _fixed_quest_key (policy_quest.py) walks to the Outpost's
  teleport building (inn, (37,119)) through _town_teleport_key and returns
  a plain key: no route declaration.  The player really moves
  (34,110) -> (33,111) -> (32,112) -> (31,113) -> (32,114) and the inn
  route closes 9 -> 8 -> 7 -> 6 -> 5 edges, but quest-request's progress
  vector held only durable facts, so 3, 4 and 5 scored no progress and
  5 retired quest-request (budget 3 -> 0).
- 6: ``town:blocked:owner-retired``.

Fix: the undeclared fixed-quest travel walk carries the inn route's
remaining edges, as the cross-town walk to the same building does.  A walk
that does not close the route repeats its vector and still retires.

Wall (declared): ``PRE_FIX`` replays with the walk predicate patched to
False (the pre-fix vector) and reproduces every live key 0..6.  With the
fix, keys 0..5 equal the live keys, so board 6 is the effect of the same
key '3' (R4); 6 is the first changed decision and the pin stops there.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import _consume_response_sequence
from hengbot.model import Position
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.policy_constants import FIXED_QUEST_TOWNS
from hengbot.town_arbiter import _new_town_turn_arbiter

from test_esp_threat_rest_recorded import EDIT, _policy

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "q2travel-progress-20261002.jsonl.gz"
BOUNDARIES = FIXTURES / "q2travel-progress-20261002.boundaries.json"
CALIBRATION = FIXTURES / "q2travel-progress-20261002.character-calibration.json"
SHA256 = {
    FIXTURE: "ee527e266abdd3dafaf23c69d2baf8f7f1c58848646cb651c98b4c61f64daf07",
    BOUNDARIES: "85887db963b60c95772e4eaa2c55f438a79fd6989d8d3d393e4710168466a2a7",
    CALIBRATION: "78ba2af16831a9a9211784eacedc74599c53de6a9dfffe68dbb5f7ae88af6220",
}
FIRST_STEP = 2
RETIRED = 5
STOP = 6
TRAVEL = "fixedquest:q2-travel"
TELEPORT = "fixedquest:q2-teleport"
INN = Position(37, 119)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _pre_fix_walk(_self, _snapshot, _reason):
    return False


class Q2TravelProgressRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path, digest in SHA256.items():
            assert _sha(path) == digest, path
        boundaries = json.loads(BOUNDARIES.read_text(encoding="utf-8"))
        fields = boundaries["recorded_fields"]
        cls.recorded = [dict(zip(fields, row)) for row in boundaries["recorded"]]
        cls.detail = boundaries["detail"]
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            lines = stream.read().splitlines(keepends=True)
        assert len(lines) == sum(boundaries["input_rows"])
        cls.segments = []
        start = 0
        for count in boundaries["input_rows"]:
            cls.segments.append(lines[start:start + count])
            start += count
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    @staticmethod
    def _post(policy, key):
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": str(key)})

    def _replay(self, last, *, pre_fix=False, inspect=None, after=None):
        """Replay the frozen process through ``last`` on one policy."""
        rows = []
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            policy = _policy(directory, self.monrace)
            policy._character_calibration_path.write_bytes(CALIBRATION.read_bytes())
            policy._crossarea_fundraising_enforced = True  # live argv
            for index in range(last + 1):
                _decoded, snapshots = _consume_response_sequence(
                    self.segments[index], policy, lambda _key: True, self.monrace,
                    knowledge_ledger_path=directory / "knowledge.jsonl",
                )
                board = snapshots[-1]
                if pre_fix:
                    # create=True: the pre-fix source has no such seam.
                    with patch.object(HengbotPolicy, "_fixed_quest_teleport_walk_reason",
                                      _pre_fix_walk, create=True):
                        key = policy.choose_key(board)
                else:
                    key = policy.choose_key(board)
                rows.append((str(key), policy.last_reason))
                if inspect is not None:
                    inspect(index, policy, board)
                self._post(policy, key)
            if after is not None:
                after(policy, board)
        return rows

    def _live(self, index):
        row = self.recorded[index]
        return row["key"], row["reason"]

    @staticmethod
    def _arbiter(policy):
        telemetry = policy._town_turn_arbiter.telemetry or {}
        return (telemetry.get("producer_owner"), telemetry.get("progress"),
                telemetry.get("retired"))

    # ------------------------------------------------------------ recorded
    def test_recorded_walk_retired_quest_request(self):
        # R1: Q2 is a Telmora (town 1) quest; the walk is in the Outpost.
        self.assertEqual(FIXED_QUEST_TOWNS[2], 1)
        positions = [tuple(self.recorded[index]["position"])
                     for index in range(FIRST_STEP, STOP + 1)]
        self.assertEqual(positions,
                         [(34, 110), (33, 111), (32, 112), (31, 113), (32, 114)])
        for index in range(FIRST_STEP, STOP):
            self.assertEqual(self._live(index)[1], TRAVEL, index)
            self.assertEqual(self.detail[str(index)]["claim"]["owner"], "quest-request")
        progress = [self.detail[str(index)]["arbiter"]["progress"]
                    for index in range(FIRST_STEP, STOP)]
        self.assertEqual(progress, [True, False, False, False])
        self.assertEqual(self.detail[str(RETIRED)]["arbiter"]["retirement_set"],
                         ["quest-request"])
        self.assertTrue(self.detail[str(RETIRED)]["arbiter"]["retired"])
        self.assertEqual(self._live(STOP), ("5", "town:blocked:owner-retired"))

    def test_pre_fix_vector_reproduces_every_live_key(self):
        rows = self._replay(STOP, pre_fix=True)
        self.assertEqual(rows, [self._live(index) for index in range(STOP + 1)])

    # ------------------------------------------------------------ fix
    def test_walk_to_the_inn_is_progress_and_continues(self):
        seen = {}

        def inspect(index, policy, board):
            if index >= FIRST_STEP:
                positions = policy._town_teleport_building_positions(board)
                route = policy._town_teleport_building_route(board, positions)
                seen[index] = (self._arbiter(policy), route.target,
                               route.remaining_edges)

        rows = self._replay(STOP, inspect=inspect)
        for index in range(STOP):
            self.assertEqual(rows[index], self._live(index), index)
        self.assertEqual([seen[index][2] for index in range(FIRST_STEP, STOP + 1)],
                         [9, 8, 7, 6, 5])
        for index in range(FIRST_STEP, STOP + 1):
            self.assertEqual(seen[index][0], ("quest-request", True, False), index)
            self.assertEqual(seen[index][1], INN, index)
        # Board 6 is the effect of the same live key '3'; first changed key.
        self.assertEqual(rows[STOP], ("3", TRAVEL), self._live(STOP))

    def test_walk_that_does_not_close_the_route_still_retires(self):
        seen = []

        def after(policy, board):
            # The walk does not move: the same board is decided again.
            for _ in range(3):
                key = policy.choose_key(board)
                seen.append((str(key), policy.last_reason, self._arbiter(policy)))
                self._post(policy, key)

        self._replay(FIRST_STEP + 1, after=after)
        self.assertEqual(seen, [
            ("9", TRAVEL, ("quest-request", False, False)),
            ("9", TRAVEL, ("quest-request", False, False)),
            ("9", TRAVEL, ("quest-request", False, True)),
        ])

    # ------------------------------------------------- constructed (declared)
    # CONSTRUCTED, not recorded: no live board of a ``fixedquest:q2-teleport``
    # walk exists.  _telmora_q2_travel_key (policy.py) and _fixed_quest_key's
    # return from Telmora (policy_quest.py) emit that reason for the same
    # _town_teleport_key walk to the current town's teleport building, so the
    # recorded boards 2..6 above (the same inn route, 9 -> 5 edges) are read
    # with that reason in place of the recorded one, and the vectors are fed
    # to a fresh arbiter.
    def _teleport_vectors(self):
        vectors = {}

        def inspect(index, policy, board):
            if index >= FIRST_STEP:
                vectors[index] = policy._town_arbiter_progress_vector(board, TELEPORT)

        self._replay(STOP, inspect=inspect)
        return [vectors[index] for index in range(FIRST_STEP, STOP + 1)]

    @staticmethod
    def _observe(arbiter, vector):
        telemetry = arbiter.observe(in_town=True, reason=TELEPORT,
                                    progress_vector=vector) or {}
        return (telemetry.get("producer_owner"), telemetry.get("progress"),
                telemetry.get("retired"))

    def test_constructed_q2_teleport_walk_is_progress(self):
        vectors = self._teleport_vectors()
        self.assertEqual([vector[-1] for vector in vectors], [
            ("locomotion", "quest-request", (0, 0, 0), INN, edges)
            for edges in (9, 8, 7, 6, 5)
        ])
        arbiter = _new_town_turn_arbiter()
        self.assertEqual([self._observe(arbiter, vector) for vector in vectors],
                         [("quest-request", True, False)] * len(vectors))

    def test_constructed_q2_teleport_walk_that_does_not_close_still_retires(self):
        first, second = self._teleport_vectors()[:2]
        arbiter = _new_town_turn_arbiter()
        rows = [self._observe(arbiter, vector)
                for vector in (first, second, second, second, second)]
        self.assertEqual(rows, [
            ("quest-request", True, False),
            ("quest-request", True, False),
            ("quest-request", False, False),
            ("quest-request", False, False),
            ("quest-request", False, True),
        ])


if __name__ == "__main__":
    unittest.main()
