"""A recall the departure authorised is not cancelled by a countdown step that changed nothing worn
(n1-a life-545, MAINTAINABILITY.md 2-3).

Recorded (tests/extract_n1a_545_recall_contradiction_1128_fixture.py,
``n1a-545-recall-contradiction-1128``): the town-arrival checkpoint of 2026-11-28 09:34 (Amberite
Rogue CL38, build bot-b60919d45), 29 rows.  Row 15 left the General Store under the forced weight
waiver (shed-sale-uncomposable), row 17 zapped the Rod of Recall for Angband (``zna``, the read
point's conjunct map all true), row 20 ate a Hard Biscuit during the countdown, and row 21
cancelled the recall as unready (``rm``, town:cancel-unready-recall).  The live decision rows show
the equipment search's verdict through the countdown: a better loadout waiting on one pack slot
(``pack-space-required:1``, ``pack-space-unrelieved-current-loadout``) with the same kit worn.  The
visit then shopped and row 28 stopped under town:blocked:recall-readiness-contradiction (the read
point refuses to read again after an unready cancel).

The canceller asked the loadout leaf (``deep-loadout-unconfirmed``) again after the eat, with
nothing worn changed.  The fix: a countdown regression must be material -- the pack fuller than at
the read (as before), or the worn kit changed (``_recall_worn_changed_since_read``) -- and every
reader of the departure reads one answer (``_departure_refusals``).

DECLARED: the equipment search's verdict is wall-clock bounded (equipment_optimizer
``timeout_seconds``) and on this machine the loadout leaf holds through the countdown, so the
replay does not cancel by itself; the stop board is read with the live verdict
(``_equipment_departure_ready`` False).  The driver's periodic character-dump request (row 5) is
in the journal's driver latches; row 5 still does not reproduce (``UNREPRODUCED``).  After row 21 the drive goes on on constructed boards: the row-21
board later in the countdown, then the arrival board (the last recorded dungeon board of this life
with the floor set to the recall's landing, the pack and kit of row 21).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.model import DUNGEON_ANGBAND, parse_snapshot
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-recall-contradiction-1128"
DUMP_ROW, READ_ROW, EAT_ROW, CANCEL_ROW = 5, 17, 20, 21
CANCEL = ("rm", "town:cancel-unready-recall")
COUNTDOWN_BOARDS = 6
# Row 5: the live driver sent the periodic character dump; the replay decides
# town:blocked:owner-retired there (the Home knowledge census posted before the restart's
# checkpoint is awaited past STORE_STUCK_LIMIT).  Listed, not asserted; the recorded key is posted.
UNREPRODUCED = (DUMP_ROW,)


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def decide(policy, board):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        key = policy.choose_key(board)
    return key, policy.last_reason, out.getvalue()


def live_loadout_verdict():
    return mock.patch.object(HengbotPolicy, "_equipment_departure_ready",
                             lambda self, *_a, **_k: False)


class RecallContradiction545RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.recorded = {row: (journal[row]["key"], journal[row]["reason"]) for row in range(len(journal))}
        cls.decided = []
        for row, (recorded, supply) in enumerate(steps[:CANCEL_ROW + 1]):
            board = supply()
            if row == CANCEL_ROW:
                cls.cancel_board, cls.cancel_checkpoint = board, checkpoint_bytes(policy)
                break
            key, reason, _ = decide(policy, board)
            cls.decided.append((key, reason))
            post(policy, recorded["key"])
        cls.raw_cancel_line = json.loads(lzma.decompress(
            (FIXTURE / "journal.jsonl.xz").read_bytes()).splitlines()[CANCEL_ROW])

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def restored(self):
        return restore_checkpoint_bytes(HengbotPolicy, self.cancel_checkpoint)

    def test_the_replay_follows_the_record_to_the_cancel(self):
        self.assertEqual(self.recorded[CANCEL_ROW], CANCEL)
        self.assertEqual(self.recorded[28][1], "town:blocked:recall-readiness-contradiction")
        self.assertEqual([row for row, decided in enumerate(self.decided)
                          if decided != self.recorded[row]], list(UNREPRODUCED))
        self.assertEqual(self.decided[READ_ROW], ("zna", "town:recall-to-angband"))
        self.assertEqual(self.decided[EAT_ROW], ("Ed", "town:eat-before-travel"))

    def test_the_countdown_changed_no_worn_item(self):
        policy, board = self.restored(), self.cancel_board
        self.assertTrue(board.player.recalling)
        self.assertFalse(policy._recall_worn_changed_since_read(board))
        self.assertFalse(policy._recall_pack_fuller_than_read(board))
        with live_loadout_verdict():
            self.assertEqual(policy._recall_unready_blockers(board, DUNGEON_ANGBAND), [])

    def test_revert_the_unchanged_kit_check_cancels_as_recorded(self):
        policy = self.restored()
        with live_loadout_verdict(), mock.patch.object(
                HengbotPolicy, "_recall_worn_changed_since_read", lambda *_: True):
            key, reason, _ = decide(policy, self.cancel_board)
        self.assertEqual((key, reason), CANCEL)

    def test_the_recall_is_kept_through_the_countdown_and_the_floor_changes(self):
        policy = self.restored()
        reasons = []
        with live_loadout_verdict():
            for step in range(COUNTDOWN_BOARDS):
                board = replace(self.cancel_board, turn=self.cancel_board.turn + 10 * step)
                key, reason, _ = decide(policy, board)
                reasons.append(reason)
                self.assertTrue(key, reason)
                self.assertNotIn("cancel", reason)
                self.assertFalse(reason.startswith("town:blocked:"), reason)
                post(policy, key)
            arrival = self.arrival_board(policy)
            key, reason, _ = decide(policy, arrival)
        self.assertTrue(all(reason.startswith("town:wait-recall") or reason.startswith("town:")
                            for reason in reasons), reasons)
        self.assertTrue(key, reason)
        self.assertFalse(reason.startswith("town:"), reason)

    def arrival_board(self, policy):
        """DECLARED CONSTRUCTED: the recall's landing (module docstring)."""
        dungeon = json.loads((FIXTURE / "arrival-dungeon-board.json").read_text(encoding="utf-8"))
        town = json.loads(self.raw_cancel_line["line"] if self.raw_cancel_line["line"] is not None
                          else self.raw_cancel_line["inputs"][-1])
        depth = self.cancel_board.dungeon_recall_depths.get(DUNGEON_ANGBAND)
        self.assertTrue(depth)
        for name in ("player", "inventory", "equipment"):
            dungeon[name] = town[name]
        dungeon["player"] = {**dungeon["player"], "recalling": False}
        dungeon["floor"] = {**dungeon["floor"], "dungeon_id": DUNGEON_ANGBAND, "level": depth}
        dungeon["turn"] = self.cancel_board.turn + 200
        return parse_snapshot(dungeon, policy._monrace_knowledge)


if __name__ == "__main__":
    unittest.main()
