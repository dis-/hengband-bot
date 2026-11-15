"""While Recall counts down: Teleportation only on 即死 or with a T1 in the line of fire (n1-a life-525).

n1-a life-525 (Lv40 Warrior) died on ガラスの城 49F on 2026-11-15 21:06:00.  It read Word of
Recall at decision 23988 and, while it counted down, read ten Teleportation scrolls in about
twelve decisions (23989-24012); the last ones at full HP (1018-1029 of 1029) on boards where no
monster had a line of fire and nothing was 即死 (the flee rung's read, the threat-tier memory
holding the earlier group T1's leave), and the last landed beside the sleeping 『スマウグ』, a
storm and 『ウリエル』.  Owner 2026-11-15, verbatim: 「即死か射線の通る T1 だけ・残り少なければ
即死だけ」 (recall_wait_teleport, asked by deep_teleport's finder and read gates).

Recorded: the boards are the incident capture's (tests/extract_n1a_525_death_1115_fixture.py:
the 21:05:39 town-arrival checkpoint replayed over the snapshot tail into the dungeon, every one
of the 135 dungeon decisions matching the record; ``policy.pkl.xz`` is that policy before
decision 23980).  From 23989 the fix decides differently from the record, so every decision
posts the recorded key (FORCED) and is compared only where the test says.

DECLARED CONSTRUCTED: ``test_few_scrolls_leave_only_instant_death`` takes 23999's board (a T1
group in the line of fire, six Teleportation scrolls) down to three scrolls.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import deep_teleport, recall_wait_teleport
from hengbot.cli import _consume_response_sequence
from hengbot.latch_onset_capture import restore_checkpoint_bytes
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-525-death-1115"
RECALL_READ = 23988
TELEPORT_KEY = "re"
# The full-HP reads on boards neither 即死 nor with a T1 in the line of fire.
WITHHELD = (24002, 24003, 24012)
INSTANT_DEATH = 24000          # 即死 (next-action p95): still read
T1_IN_FIRE = (23997, 23999)    # a T1 group with a line of fire, more than three scrolls: still read


class N1a525RecallWaitTeleport1115RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        policy_bytes = lzma.decompress((FIXTURE / "policy.pkl.xz").read_bytes())
        cls.boards = [json.loads(line) for line in lzma.decompress(
            (FIXTURE / "boards.jsonl.xz").read_bytes()).decode("utf-8").splitlines() if line]
        cls.policy = restore_checkpoint_bytes(HengbotPolicy, policy_bytes)
        cls.scratch = TemporaryDirectory()
        ledger = Path(cls.scratch.name) / "knowledge.jsonl"
        cls.decided = {}
        for entry in cls.boards:
            recorded = entry["decision"]
            _consume_response_sequence(
                [json.dumps(record, ensure_ascii=False) + "\n" for record in entry["inputs"]],
                cls.policy, lambda _key: True, cls.policy._monrace_knowledge,
                parse_snapshots=False, knowledge_ledger_path=ledger)
            board = parse_snapshot(json.loads(json.dumps(entry["inputs"][-1])),
                                   cls.policy._monrace_knowledge)
            key = cls.policy.choose_key(board)
            cls.decided[recorded["decision_sequence"]] = (
                recorded, board, key, cls.policy.last_reason, deep_teleport.report(cls.policy))
            cls.policy.confirm_key_posted(recorded["key"])  # FORCED

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_the_record_reads_ten_teleports_while_recalling(self):
        read = self.decided[RECALL_READ][0]
        self.assertEqual((read["key"], read["reason"]), ("rf", "return:recall"))
        reads = [sequence for sequence, (recorded, board, *_rest) in self.decided.items()
                 if board.player.recalling and recorded["key"] == TELEPORT_KEY]
        self.assertEqual(len(reads), 10)
        for sequence in WITHHELD:
            recorded, board, *_rest = self.decided[sequence]
            self.assertEqual(recorded["reason"], "flee:scroll")
            self.assertTrue(board.player.recalling)
            self.assertGreaterEqual(board.player.hp, 1018)
            self.assertEqual(board.player.max_hp, 1029)

    def test_the_full_hp_boards_read_no_teleport(self):
        for sequence in WITHHELD:
            _recorded, board, key, reason, report = self.decided[sequence]
            self.assertNotEqual(key, TELEPORT_KEY, sequence)
            self.assertEqual((key, reason), ("5", "flee:wait"), sequence)
            self.assertEqual(report, {"branch": recall_wait_teleport.BRANCH, "turn": board.turn})

    def test_instant_death_and_a_t1_in_fire_still_read(self):
        for sequence in (INSTANT_DEATH, *T1_IN_FIRE):
            _recorded, board, key, reason, report = self.decided[sequence]
            self.assertTrue(board.player.recalling)
            self.assertEqual((key, reason), (TELEPORT_KEY, "emergency:teleport"), sequence)
            self.assertIsNone(report, sequence)

    def test_few_scrolls_leave_only_instant_death(self):
        _recorded, board, *_rest = self.decided[T1_IN_FIRE[1]]
        self.assertEqual(self.policy._count_teleport_scrolls(board), 6)
        # DECLARED CONSTRUCTED: three Teleportation scrolls left.
        few = replace(board, inventory=[
            replace(item, count=recall_wait_teleport.FEW_SCROLLS) if item.is_teleport_scroll
            else item for item in board.inventory])
        self.assertEqual(self.policy._count_teleport_scrolls(few), recall_wait_teleport.FEW_SCROLLS)
        self.assertTrue(recall_wait_teleport.withheld(self.policy, few))

    def test_before_the_recall_the_rule_does_not_apply(self):
        recorded, board, key, reason, _report = self.decided[RECALL_READ - 1]
        self.assertFalse(board.player.recalling)
        self.assertEqual((key, reason), (recorded["key"], recorded["reason"]))
        self.assertEqual(reason, "flee:scroll")
        self.assertFalse(recall_wait_teleport.withheld(self.policy, board))


if __name__ == "__main__":
    unittest.main()
