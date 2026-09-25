"""Recorded pin: the town read point and the recall canceller judge one board.

Live incident 2026-09-25 14:52-14:53 (bot process started 14:22; stopped by
the operator): in town, target = alternate = 7 (Forest), nine round trips in
under two minutes.  ``town:recall-to-alt-dungeon`` read a Word of Recall
('rje'), the very next decision ``town:cancel-unready-recall`` read another one
to cancel it ('rj'; from the second pair on, the posting contract first
refused it as ``posting-contract:recall-already-active`` and the canceller
reposted after 'l\\x1b'), the town bought the two scrolls back at the
Alchemist ('ph2'), and the pair repeated until the scrolls ran out
(``town:recall-stockout-mining``, sequence 5989).

Root cause (the failed leaf is ``free_pack_slots_ready``): the pack held 19
items, 4 free slots, below MIN_FREE_PACK_SLOTS (5).  Four slots pass only
through the terminal four-slot certificate (``_town_pack_space_ready``), which
signs the exact pack including every stack count.  The read point judged the
certificate on the read board (recall stack 11) and read; the read itself took
the stack to 10, so on the next board the canceller -- which runs early in
``_decide``, before the terminal fallback that re-signs the certificate --
found ``pack-too-full`` and cancelled.  The read's own consumption voided the
readiness that authorised it.  Buying the two scrolls back restored the signed
pack, so the read point read again.  Not a regression of the 2026-09-25
commits: the same boards cancel identically on 157e5010 (2026-09-24) and on
the parents of 3b3f2ec8, 5075ef66, 9f2364cb, c1a4abb5 and 6168c9fa.

Fix (one source): the canceller's blockers are leaves of the read point's own
conjunct map (``_recall_town_departure_conjuncts``), evaluated on
``_recall_departure_board`` -- the board the armed read was authorised on,
with exactly the read's own effect (one scroll, the armed recall) undone.
Class bound: once a recall was cancelled as unready, the read point does not
read again in the same town visit (tests/test_recall_read_cancel_pingpong.py).

Substrate (tests/extract_recall_read_cancel_pingpong_fixture.py): for each of
the nine recorded reads, the read decision's and the following cancel
decision's own input rows and recorded facts, and the landing's ~f skill list.
Each pair is replayed on a fresh policy through the public response path.
Walls, each declared:
- attach: the policy is primed on the read board, as a resumed process
  attaches, and then receives this visit's ~f skill list (the landing's
  response), so the read board is not spent on the probe;
- the calibration file is the one the process wrote at 14:23:36, in a
  temporary directory, with the Home history/disposal files;
- visit facts a fresh process cannot rebuild from these boards (they encode
  the process's town history before the frozen rows) are taken from the read
  decision's own record: the recall target and alternate
  (``over_extension``), ``home_scan_complete``, ``identification_need`` and
  ``home_candidate_waiting``; the pre-dive character dump is done and
  ``_equipment_departure_ready`` holds -- the recorded read proves both, the
  ordinary rung reads only after the dump and with every departure leaf true;
- the four-slot certificate equals the read board's pack signature: the
  recorded read proves it (19 items, free 4 < 5, so ``free_pack_slots_ready``
  held only through the certificate);
- read decision, ladder: the fresh policy's ladder ranks this process's
  earlier Home/equipment work differently, so the read decision runs the
  recorded winning rung's real producer (``_town_special_key``); the choose_key
  entry and exit seams are production code.  The cancel decision runs the whole
  production ``choose_key``;
- the cancel board carries the live input executor's
  ``_completed_operation_sequence``/``_owner`` of the posted read.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import MIN_FREE_PACK_SLOTS, PACK_CAPACITY

from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "recall-read-cancel-pingpong-20260925.jsonl.gz"
CALIBRATION = FIXTURES / (
    "recall-read-cancel-pingpong-20260925.character-calibration.json"
)
FIXTURE_SHA256 = "b68d2fdf326b6639dea2ad51581a06ddaac3516d00184cb9794eea3a8e206867"
BOUNDARIES_SHA256 = (
    "66f9a58878f2a95d5a3833e82fac7011d7def4beae77920fc77044b989be6f9f"
)
CALIBRATION_SHA256 = (
    "b78abdb573ec899a735b60badc0dec52e4e66a04b22a054e928e2cc4b4450148"
)
READ = ("rje", "town:recall-to-alt-dungeon")
CANCEL = ("rj", "town:cancel-unready-recall")
PAIRS = (
    (5911, 5912), (5917, 5918), (5924, 5925), (5931, 5932), (5938, 5939),
    (5945, 5946), (5956, 5957), (5978, 5979), (5985, 5986),
)
FOREST = 7
# What the fixed policy emits on each recorded cancel board instead: the
# armed recall is kept and the character steps off the store entrance it
# read on (the ordinary wait for an armed town recall).
STEP_OFF = "town:wait-recall-step-off"
STEP_OFF_KEYS = ("1", "7", "7", "7", "7", "7", "1", "1", "1")


class RecallReadCancelPingPongRecordedTest(unittest.TestCase):
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
        boundaries = json.loads(boundaries_path.read_text(encoding="utf-8"))
        fields = boundaries["recorded_fields"]
        cls.recorded = [dict(zip(fields, row)) for row in boundaries["recorded"]]
        cls.skill = boundaries["attach_skill_knowledge"]
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.lines = list(stream)
        assert len(cls.lines) == sum(boundaries["input_rows"])
        assert len(cls.recorded) == 2 * len(PAIRS)
        cls.starts = [0]
        for count in boundaries["input_rows"]:
            cls.starts.append(cls.starts[-1] + count)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    @classmethod
    def _segment(cls, index):
        segment = cls.lines[cls.starts[index] : cls.starts[index + 1]]
        if index % 2:
            # Wall (executor binding): the cancel board follows the posted read.
            previous = cls.recorded[index - 1]
            row = json.loads(segment[-1])
            row["_completed_operation_sequence"] = previous["decision_sequence"]
            row["_completed_operation_owner"] = previous["reason"]
            segment = segment[:-1] + [json.dumps(row, ensure_ascii=False) + "\n"]
        return segment

    @classmethod
    def _board(cls, policy, index, directory):
        _decoded, snapshots = _consume_response_sequence(
            cls._segment(index), policy, lambda _key: True, cls.monrace,
            knowledge_ledger_path=directory / "knowledge.jsonl",
        )
        return snapshots[-1]

    @classmethod
    def _pair(cls, pair):
        read_index, cancel_index = 2 * pair, 2 * pair + 1
        record = cls.recorded[read_index]
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            policy = _policy(directory, cls.monrace)
            policy._character_calibration_path.write_bytes(
                CALIBRATION.read_bytes()
            )
            read_board = cls._board(policy, read_index, directory)
            # Wall (attach): see the module docstring.
            policy.prime(read_board)
            policy.consume_skill_knowledge(cls.skill)
            # Wall (visit facts): from the read decision's own record.
            policy._target_dungeon_id = record["target_dungeon_id"]
            policy._alternate_dungeon = record["alternate_dungeon_id"]
            policy._equipment_catalog.home_scan_complete = record[
                "home_scan_complete"
            ]
            policy._identification_need = record["identification_need"]
            policy._home_candidate_waiting = record["home_candidate_waiting"]
            policy._char_dump_done_this_visit = True
            # Wall (certificate): see the module docstring.
            policy._terminal_pack_space_signature = (
                policy._town_pack_space_signature(read_board)
            )
            read_signature = policy._town_pack_space_signature(read_board)
            with patch.object(
                policy, "_equipment_departure_ready", return_value=True
            ):
                with patch.object(
                    policy, "_choose_key_with_latch_capture",
                    side_effect=policy._town_special_key,
                ):
                    read_key = policy.validate_read_key(
                        read_board, policy.choose_key(read_board)
                    )
                read = (read_key, policy.last_reason)
                policy.confirm_key_posted(read_key)
                cancel_board = cls._board(policy, cancel_index, directory)
                raw_leaves = policy._recall_town_departure_conjuncts(cancel_board)
                departure_board = policy._recall_departure_board(cancel_board)
                result = {
                    "read": read,
                    "read_board": read_board,
                    "cancel_board": cancel_board,
                    "read_signature": read_signature,
                    "raw_failed": [k for k, ok in raw_leaves.items() if not ok],
                    "raw_pack_ready": policy._town_pack_space_ready(cancel_board),
                    "departure_signature": policy._town_pack_space_signature(
                        departure_board
                    ),
                    "blockers": policy._recall_unready_blockers(
                        cancel_board, policy._pending_recall_dungeon_id
                    ),
                }
                cancel_key = policy.validate_read_key(
                    cancel_board, policy.choose_key(cancel_board)
                )
                result["cancel"] = (cancel_key, policy.last_reason)
                result["cancelled_flag"] = getattr(
                    policy, "_town_visit_unready_recall_cancelled", False
                )
        return result

    @classmethod
    def _replay(cls):
        if cls.replay is None:
            cls.replay = [cls._pair(pair) for pair in range(len(PAIRS))]
        return cls.replay

    # ------------------------------------------------------------ recorded
    def test_recorded_pairs_are_a_read_then_its_unready_cancel(self):
        recorded = self.recorded
        self.assertEqual(
            [
                (recorded[2 * p]["decision_sequence"],
                 recorded[2 * p + 1]["decision_sequence"])
                for p in range(len(PAIRS))
            ],
            list(PAIRS),
        )
        for pair in range(len(PAIRS)):
            read, cancel = recorded[2 * pair], recorded[2 * pair + 1]
            self.assertEqual((read["key"], read["reason"]), READ)
            self.assertEqual(read["read_key"], READ[0])
            self.assertEqual((cancel["key"], cancel["reason"]), CANCEL)
            self.assertEqual(
                (read["target_dungeon_id"], read["alternate_dungeon_id"]),
                (FOREST, FOREST),
            )
            # 19 items, 4 free: below MIN_FREE_PACK_SLOTS on every read.
            self.assertEqual(
                (read["inventory_used"], read["inventory_free"]), (19, 4)
            )
            self.assertEqual(read["inventory_free"], PACK_CAPACITY - 19)
            self.assertLess(read["inventory_free"], MIN_FREE_PACK_SLOTS)
            self.assertEqual(cancel["inventory_used"], 19)
        # The posting contract refused the first cancel read of every pair
        # after the first (the canceller reposted after 'l\x1b').
        self.assertEqual(
            [recorded[2 * p + 1]["posting_refused"] for p in range(len(PAIRS))],
            [False] + [True] * (len(PAIRS) - 1),
        )

    def test_the_read_alone_changes_the_signed_pack(self):
        for pair, result in enumerate(self._replay()):
            with self.subTest(pair=PAIRS[pair]):
                read_board = result["read_board"]
                cancel_board = result["cancel_board"]
                self.assertFalse(read_board.player.recalling)
                self.assertTrue(cancel_board.player.recalling)
                read_recall = [i for i in read_board.inventory if i.is_recall_scroll]
                cancel_recall = [
                    i for i in cancel_board.inventory if i.is_recall_scroll
                ]
                self.assertEqual(len(read_recall), 1)
                self.assertEqual(
                    cancel_recall[0].count, read_recall[0].count - 1
                )
                # The certificate's pack differs from the cancel board's in
                # exactly the recall stack's count.
                changed = set(result["read_signature"]) ^ set(
                    (i.slot, i.name, i.tval, i.sval, i.count)
                    for i in cancel_board.inventory
                )
                self.assertEqual(
                    {entry[0] for entry in changed}, {read_recall[0].slot}
                )

    # ------------------------------------------------------------ fidelity
    def test_replay_reproduces_each_recorded_read(self):
        self.assertEqual(
            [result["read"] for result in self._replay()], [READ] * len(PAIRS)
        )

    def test_the_failed_leaf_on_each_cancel_board_is_the_pack_certificate(self):
        """The recorded cancel's failed leaf, judged on the raw cancel board."""
        for pair, result in enumerate(self._replay()):
            with self.subTest(pair=PAIRS[pair]):
                self.assertFalse(result["raw_pack_ready"])
                self.assertEqual(result["raw_failed"], ["free_pack_slots_ready"])

    # ------------------------------------------------------------ R1
    def test_r1_cancel_boards_keep_the_armed_recall(self):
        """Fixed: each recorded cancel board keeps the recall the read armed.

        The canceller judges the read board (the read's own scroll undone),
        whose pack is the certified one, so it finds no blocker; the decision
        is the ordinary wait for an armed recall -- stepping off the store
        entrance the read was made on -- instead of the recorded 'rj'.
        """
        replay = self._replay()
        for pair, result in enumerate(replay):
            with self.subTest(pair=PAIRS[pair]):
                self.assertEqual(
                    result["departure_signature"], result["read_signature"]
                )
                self.assertEqual(result["blockers"], [])
                self.assertFalse(result["cancelled_flag"])
        self.assertEqual(
            [result["cancel"] for result in replay],
            [(key, STEP_OFF) for key in STEP_OFF_KEYS],
        )


if __name__ == "__main__":
    unittest.main()
