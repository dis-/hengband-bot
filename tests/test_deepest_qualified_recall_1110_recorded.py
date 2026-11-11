"""n1-b life-365 2026-11-10 16:28: no recall landing qualifies -> the deepest that does, else funds.

Recorded: tests/fixtures/yeek-exit-loops-1110/depth-gate-1628.json.gz
(tests/extract_yeek_exit_loops_1110_fixtures.py), the restarted process of n1-b life-365
(Magic-Eater Lv32, Outpost, build c6e2443b2) from its first board to the third
``town:blocked:owner-retired-burst`` (after which the character was retired).  The recall
target was the Castle (the over-extension alternate), whose landing had become 51 and needs
*Destruction* and telepathy; every decision of the visit stopped on
``town:blocked:depth-gate:destination-51:missing-destruction,telepathy``: the unsafe-recall
fallback took no dungeon (Angband was never a fallback; the Mountain 49 and the Orc cave 22
are guardian floors the kit cannot pass; the conquered maze, the Forest, the Chameleon cave
and the Yeek cave are never fallbacks) and the no-safe-destination fundraising refused a
missing *Destruction*.

Owner answer 2026-11-10: 「条件を満たす一番深い所へ」 -- 「入ったダンジョンのうち、深さの
条件を満たす帰還の階で一番深い所へ行く（11-10 の「収まる中で一番深い所へ」と同じ考え）。
どこも満たさなければ資金集め。」  Combined with the same day's 「収まる中で一番深い所へ」 (the
over-extension switch): with an over-extension recorded, the landing must also be strictly
shallower than the over-extended depth.  Here the over-extended depth is 49, so Angband 49
(which needs nothing the kit lacks) is excluded by that rule, nothing qualifies, and the
character fundraises.  With the over-extended depth constructed at 50, Angband 49 is taken.

The process is a fresh policy (tests.support.recorded._policy) fed the recorded rows through
the live consumption path (cli._consume_response_sequence) and ``choose_key``; its first
board restores the switch from the alternate-dungeon record as the live process did.
DECLARED RECONSTRUCTED: that record (alternate the Castle, the too-deep depth 49, as every
decision row's ``over_extension`` shows; the reason ``over_extended_dives``, the one that
sets that depth; the counters 0).  DECLARED COMPONENT PIN with a WALL: the decision is the
town owner that holds the depth gate (``_town_special_key``) on the recorded gate board,
with ``_town_claims_active`` walled to False -- the live process's store pages and its
``bA`` staff list are not in the capture, so a fresh process still has shop errands on this
board (the live one had finished them: its rows 7-15 are the gate).  On that wall the
unfixed code returns the recorded stop (``test_the_recorded_gate_stop_on_the_wall``).
DECLARED CONSTRUCTED: the Angband cases record the over-extended depth 50 instead of 49.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from hengbot.cli import _consume_response_sequence
from hengbot.model import DUNGEON_ANGBAND
from tests.support.recorded import _policy
from tests.test_n1b_348_stops_1108_recorded import knowledge

FIXTURE = Path(__file__).with_name("fixtures") / "yeek-exit-loops-1110" / "depth-gate-1628.json.gz"
CASTLE, MOUNTAIN = 12, 14
GATE_BOARD = 4990136  # the restarted process's first depth-gate decision (row 7)
STOP = "town:blocked:depth-gate:destination-51:missing-destruction,telepathy"
OVEREXTENDED_ANGBAND_FITS = 50  # DECLARED CONSTRUCTED (module docstring)
RECORD = {"conquered": [2, 4], "state": {
    "_alternate_dungeon": CASTLE, "_alternate_dungeon_reason": "over_extended_dives",
    "_last_overextended_depth": 49, "_target_empty_dives": 0, "_guardian_bounce_dives": 0,
    "_no_depth_progress_dives": 0}}

with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)


class DeepestQualifiedRecallTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.scratch = Path(directory.name)
        self.record = self.scratch / "alternate-dungeon.json"
        self.write_record(RECORD["state"]["_last_overextended_depth"])

    def write_record(self, overextended):
        record = copy.deepcopy(RECORD)
        record["state"]["_last_overextended_depth"] = overextended
        self.record.write_text(json.dumps(dict(record, turn=CASE["rows"][0]["turn"])) + chr(10),
                               encoding="utf-8")

    def process(self, name, rows, *, until=GATE_BOARD):
        """A fresh process fed ``rows`` up to the board of turn ``until``."""
        folder = self.scratch / name
        folder.mkdir()
        races = knowledge(CASE)
        policy = _policy(folder, races)
        policy._alternate_dungeon_record_path = self.record
        board = None
        for row in rows:
            line = json.dumps(row, ensure_ascii=False) + "\n"
            _decoded, snapshots = _consume_response_sequence(
                [line], policy, lambda _key: True, races,
                knowledge_ledger_path=folder / "knowledge.jsonl")
            for snapshot in snapshots:
                board = snapshot
                if snapshot.turn >= until:
                    return policy, board
                key = policy.choose_key(snapshot)
                if key:
                    policy.confirm_key_posted(str(key))
        raise AssertionError(f"board {until} not recorded")

    @staticmethod
    def gate(policy, board):
        policy._town_claims_active = lambda _snapshot: False  # DECLARED WALL (docstring)
        key = policy._town_special_key(board)
        return key, policy.last_reason

    def test_recorded_rows(self):
        reasons = [row["reason"] for row in CASE["decisions"]]
        self.assertEqual(reasons[7:16], [STOP] * 9)
        self.assertEqual(reasons[16], "town:blocked:owner-retired-burst")
        board = next(row for row in CASE["rows"] if row["turn"] == GATE_BOARD)
        progress = board["progress"]
        self.assertEqual(progress["recall_dungeon_id"], CASTLE)
        self.assertEqual(progress["dungeon_recall_depths"],
                         {"1": 49, "12": 51, "14": 49, "18": 30, "2": 13, "3": 22, "4": 18, "7": 15})

    def test_the_recorded_gate_stop_on_the_wall(self):
        # The wall reproduces the live decision's inputs: the restored switch (the Castle)
        # and its refused landing.
        policy, board = self.process("live", CASE["rows"])
        self.assertEqual((policy._alternate_dungeon, policy._target_dungeon_id), (CASTLE, CASTLE))
        self.assertEqual(policy._missing_required_abilities(board, 51),
                         frozenset({"destruction", "telepathy"}))
        self.assertEqual(policy._missing_required_abilities(board, 49), frozenset())
        # Owner 2026-11-11 (C2) 「能力的には64Fから成果を得るのに十分である。」: the Mountain 49,
        # the floor above its guardian floor 50, is a landing now (live: refused as one).
        self.assertTrue(policy._fallback_landing_allowed(board, MOUNTAIN, 49))

    def test_the_deepest_qualified_landing_is_angband(self):
        self.write_record(OVEREXTENDED_ANGBAND_FITS)
        policy, board = self.process("live", CASE["rows"])
        key, reason = self.gate(policy, board)
        # Unfixed: ('5', STOP), the recorded stop.
        self.assertEqual((key, reason), ("5", "town:unsafe-recall-fallback"))
        self.assertEqual(policy._target_dungeon_id, DUNGEON_ANGBAND)
        self.assertEqual(policy._alternate_dungeon, DUNGEON_ANGBAND)
        self.assertEqual(policy._alternate_dungeon_reason, "safe_fallback")
        self.assertEqual(board.dungeon_recall_depths[DUNGEON_ANGBAND], 49)

    def test_a_restart_keeps_angband(self):
        self.write_record(OVEREXTENDED_ANGBAND_FITS)
        policy, board = self.process("live", CASE["rows"])
        self.gate(policy, board)
        later = [row for row in CASE["rows"] if row["turn"] > GATE_BOARD]
        # The next board's observation writes the switch to the record.
        self.assertIsNotNone(policy.choose_key(_board(policy, later[0])))
        self.assertEqual(json.loads(self.record.read_text(encoding="utf-8"))["state"]
                         ["_alternate_dungeon"], DUNGEON_ANGBAND)
        # DECLARED: the restarted process's ~f and ~9 answers are this capture's recorded
        # ones (turn 4990125, the same visit), each after the board that asks it.
        answers = [row for row in CASE["rows"] if row.get("type") == "knowledge"]
        restart_rows = [later[0], answers[0], later[1], answers[1], later[2], later[3]]
        restarted, _board_ = self.process("restart", restart_rows, until=later[3]["turn"])
        # Unfixed: the Castle comes back (no fallback was ever switched to).
        self.assertEqual(restarted._alternate_dungeon, DUNGEON_ANGBAND)
        self.assertEqual(restarted._target_dungeon_id, DUNGEON_ANGBAND)

    def test_below_the_over_extension_the_orc_cave_22_is_taken(self):
        """Live and until owner 2026-11-11 (C2): nothing shallower than 49 qualified (the Orc
        cave 22 read as its guardian floor) and the character fundraised.  The Orc cave's
        guardian floor is 23; 22 is the deepest landing shallower than 49 now (「条件を満たす
        一番深い所へ」)."""
        policy, board = self.process("none", CASE["rows"])
        # Angband 49 meets the depth gate but is not shallower than the over-extended 49.
        self.assertEqual(policy._last_overextended_depth, 49)
        self.assertEqual(board.dungeon_recall_depths[DUNGEON_ANGBAND], 49)
        self.assertEqual(policy._missing_required_abilities(board, 49), frozenset())
        key, reason = self.gate(policy, board)
        self.assertEqual((key, reason), ("5", "town:unsafe-recall-fallback"))
        self.assertEqual((policy._alternate_dungeon, policy._target_dungeon_id), (3, 3))
        self.assertEqual(board.dungeon_recall_depths[3], 22)
        # A restarted process on the same board decides the same (the set is re-derived).
        again, board = self.process("none-restart", CASE["rows"])
        self.assertEqual(self.gate(again, board)[1], reason)


def _board(policy, row):
    line = json.dumps(row, ensure_ascii=False) + "\n"
    _decoded, snapshots = _consume_response_sequence(
        [line], policy, lambda _key: True, policy._monrace_knowledge)
    return snapshots[-1]


if __name__ == "__main__":
    unittest.main()
