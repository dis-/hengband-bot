"""n1-a (warrior) life-502 2026-11-09 21:24: twelve character dumps at one game turn.

Recorded: tests/fixtures/n1a-502-dump-loop-1109/
(tests/extract_n1a_502_dump_loop_1109_fixture.py), the town-arrival checkpoint of the
first loop-detected stop (arrival turn 1015711).  Every decision is the public
``choose_key``; the dump key goes through the production executor port.

Back from the dungeon, the town decisions asked the Home retention view of the
equipment plan's projected loadout (``_transaction_retain_identities``: the board with
the body armour's slot taken off).  Its quest-force check measured the main weapon with
``_validated_character_calibration(projected)``, which compared the projection's gear
with the displayed stats, still the worn board's (STR 18/121 with the +1 STR armour).
They disagreed ("visible-current-changed"): the calibration was dropped and a dump
requested.  The dump's board re-derived the same calibration, and the next decision's
projection dropped it again, so 'Cf\\ry' went out at every decision with no game turn
(the game answered 「キャラクタ情報のファイルへの書き出しに成功しました。」 <x12>).  Now only
the board being decided can invalidate the calibration; a projection is not an
observation of the character.

DECLARED CONSTRUCTED: the game writes the dump file while it handles the posted macro;
the test writes the recorded file again (same bytes, a fresh mtime) at that point.  The
C screens of the executor exchange are the measured warrior screens of
tests/fixtures/me-dump-stuck-20261029.json.gz (test_character_dump_more_recorded).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import hashlib
import json
import lzma
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import unittest

from hengbot.home_disposal import HOME_HISTORY_DIR_ENV
from hengbot.policy import CHARACTER_DUMP_MACRO, staged_prompt_chain_matches
from hengbot.runtime_paths import RUNTIME_DIR_ENV
from hengbot.town_arrival_checkpoint import (
    JOURNAL_FILE, POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST)
from replay_town_arrival import adopt_calibration, decisions, restore
import test_character_dump_more_recorded as dump_pins

FIXTURES = Path(__file__).with_name("fixtures") / "n1a-502-dump-loop-1109"
DUMP_ROW = 2
DUMP = "periodic:character-dump"


class DumpLoopRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = dump_pins.FIXTURE.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == dump_pins.SHA256
        cls.screens = json.loads(gzip.decompress(raw))["measured"]["warrior_template"]

    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)
        for name in ("runtime-env", "history-env", "runtime"):
            (self.scratch / name).mkdir()
        env = mock.patch.dict(os.environ, {
            RUNTIME_DIR_ENV: str(self.scratch / "runtime-env"),
            HOME_HISTORY_DIR_ENV: str(self.scratch / "history-env")})
        env.start()
        self.addCleanup(env.stop)

    def visit(self):
        visit = self.scratch / "town-arrival"
        (visit / SIDECAR_DIRECTORY).mkdir(parents=True)
        (visit / POLICY_FILE).write_bytes(lzma.decompress((FIXTURES / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            lzma.decompress((FIXTURES / "journal.jsonl.xz").read_bytes())))
        sidecars = json.loads(lzma.decompress((FIXTURES / "sidecars.json.xz").read_bytes()))
        (visit / SIDECAR_MANIFEST).write_text(json.dumps(sidecars["manifest"]), encoding="utf-8")
        for role, text in sidecars["files"].items():
            (visit / SIDECAR_DIRECTORY / role).write_bytes(text.encode("latin-1"))
        return visit

    @staticmethod
    def post(policy, key):
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def to_dump_row(self):
        """Rows 0-1 (two rests) decide as recorded; return the row-2 board."""
        visit, runtime = self.visit(), self.scratch / "runtime"
        policy = restore(visit, runtime)
        adopt_calibration(policy, visit / SIDECAR_DIRECTORY / "_character_calibration_path", runtime)
        rows = decisions(policy, visit, runtime)
        for recorded, supply in rows:
            board = supply()
            if recorded["row"] == DUMP_ROW:
                return policy, board, rows
            key = policy.choose_key(board)
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]),
                             recorded["row"])
            self.post(policy, key)
        self.fail("the journal ends before the dump row")

    def test_the_projected_loadout_leaves_the_calibration_standing(self):
        policy, board, _rows = self.to_dump_row()
        # The worn +1 STR armour is in the board's STR 18/121.
        body = next(item for item in board.equipment if item.slot == "body")
        self.assertEqual((body.pval, 0 in body.known_flags), (1, True))
        self.assertEqual(board.player.stat_use[0], 139)
        self.assertIsNotNone(policy._validated_character_calibration(board))
        key = policy.choose_key(board)
        self.assertNotEqual(policy.last_reason, DUMP)
        self.assertNotEqual(key, CHARACTER_DUMP_MACRO)
        self.assertIsNotNone(policy._character_calibration)
        self.assertIsNone(policy._calibration_unavailable_reason)
        self.assertFalse(policy._periodic_dump_requested)

    def test_one_due_dump_is_sent_recorded_and_not_repeated(self):
        policy, board, rows = self.to_dump_row()
        # The CLI's wall-clock period is due (cli._request_due_dump).
        policy.request_character_dump()
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), (CHARACTER_DUMP_MACRO, DUMP))
        peer = dump_pins.DumpPeer(self.screens)
        dump_pins.CharacterDumpMoreRecordedTest.send_dump(self, peer, key, policy, board)
        self.assertEqual(peer.phase, "done")
        self.post(policy, key)
        # DECLARED CONSTRUCTED (module docstring): the game wrote the dump.
        dump = Path(policy._character_dump_path)
        dump.write_bytes(dump.read_bytes())
        now = time.time_ns()
        os.utime(dump, ns=(now, now))
        recorded, supply = next(rows)
        after = supply()
        # The recorded responses: the C sheet's character snapshot, then the board.
        self.assertEqual(after.turn, board.turn)
        key = policy.choose_key(after)
        self.assertEqual((recorded["key"], recorded["reason"]), (CHARACTER_DUMP_MACRO, DUMP))
        self.assertNotEqual(key, CHARACTER_DUMP_MACRO)
        self.assertNotEqual(policy.last_reason, DUMP)
        # The dump was read and recorded: a fresh calibration from this board.
        calibration = policy._character_calibration
        self.assertIsNotNone(calibration)
        self.assertIsNone(policy._calibration_rejection)
        self.assertEqual(calibration.observed_turn, after.turn)
        self.assertIsNone(policy._calibration_dump_pending)
        self.assertFalse(policy._periodic_dump_requested)


if __name__ == "__main__":
    unittest.main()
