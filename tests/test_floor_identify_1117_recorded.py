"""A plain unidentified weapon or armour is identified on the floor, not picked up first (1117).

Owner 2026-11-17 (verbatim 「今のまま取りに行き、床の上で鑑定」; floor_identify's docstring has the
game's chooser and the auto-destroy): the loot walk still goes to it; standing on a one-object pile
of it the bot uses its identify with the floor choice ``-``, and the pick rules destroy it there.

Recorded (tests/fixtures/deep-efficiency-1117-floor-identify.jsonl.gz, see
tests/extract_deep_efficiency_1117_fixtures.py): n1-c life-216 (Magic-Eater), Glass castle 49F,
2026-11-17 15:43:34, turns 5629080-5629130: ``seek-loot`` to (6,150), ``pickup`` 'g' of 「戦闘用つる
はし (1d8)」, ``identify:dungeon-equipment`` 'mAfo' and 「戦闘用つるはし (1d8) (-3,-3) (-2) {呪われ
ている}を自動破壊します。」; then the same for 「二重リングメイル [15]」 at (5,150).  DECLARED
RECONSTRUCTED: the absorbed Identify's record (30 charges at 98%; the snapshots keep no power list,
the record cast 'mAf').
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import magic_eater_input, me_capability, me_staff_sequence
from hengbot.model import SV_STAFF_IDENTIFY, Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "deep-efficiency-1117-floor-identify.jsonl.gz"
PICKAXE, MAIL = 5629110, 5629118
REASON = "loot:identify-floor-item"


class FloorIdentifyRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.boards = [json.loads(line) for line in stream if line.strip()]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        directory = TemporaryDirectory()
        cls.directory = directory
        policy = _policy(Path(directory.name), cls.monrace)
        first = parse_snapshot(copy.deepcopy(cls.boards[0]), cls.monrace)
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        policy._me_device_lists = {"staff": (first.turn, ({
            "name": me_capability.names("staff", SV_STAFF_IDENTIFY)[0], "current": 30,
            "max": 30, "fail": 2, "success": 98},))}
        me_staff_sequence.state(policy).absorbed[me_capability.record_key("staff", SV_STAFF_IDENTIFY)] = 30
        cls.rows = {}
        for raw in cls.boards:
            board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), cls.monrace))
            key = policy.choose_key(board)
            cls.rows[board.turn] = (key, policy.last_reason, board)
            if key:
                policy.confirm_key_posted(key)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_standing_on_the_pickaxe_identifies_it_on_the_floor(self):
        key, reason, board = self.rows[PICKAXE]
        self.assertEqual(board.player.position, Position(6, 150))
        self.assertEqual(board.grid_at(board.player.position).object_count, 1)
        self.assertEqual((key, reason), ("mAf-", REASON))

    def test_standing_on_the_ring_mail_identifies_it_on_the_floor(self):
        key, reason, board = self.rows[MAIL]
        self.assertEqual(board.player.position, Position(5, 150))
        self.assertEqual((key, reason), ("mAf-", REASON))

    def test_the_executor_takes_the_floor_target(self):
        """The Magic-Eater menu walk answers the identify prompt with ``-`` (magic_eater_input)."""
        prefix, steps = magic_eater_input.compile_magic_eater("mAf-", REASON)
        self.assertEqual(prefix, "m")
        self.assertEqual((steps[0].kind, steps[0].sval, steps[0].target), ("staff", 5, "-"))
        with self.assertRaises(ValueError):
            magic_eater_input.compile_magic_eater("mAk-", REASON)

    def test_the_walk_to_the_pile_is_unchanged(self):
        self.assertTrue(any(reason == "seek-loot" for _key, reason, board in self.rows.values()
                            if board.turn < PICKAXE))


if __name__ == "__main__":
    unittest.main()
