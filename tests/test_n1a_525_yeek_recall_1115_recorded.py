"""An active recall ends the fundraising return's walk at every depth (n1-a life-525).

n1-a life-525 (Lv37 Warrior, build 3b52c43f0) stopped on Yeek cave 1F on 2026-11-15
12:47:51 (loop-detected).  Its mining run's return walked fundraise:seek-upstairs '3' from
(41,22) to (42,23) and '7' back: from (42,23) a 白イモムシの大群 in the corridor to the stairs
was in view and the route went round it, from (41,22) it was out of sight and the corridor
was the route again.  The ping-pong guard saw the pair (decision 82661) and escalated
(82666), and the livelock leave read Recall (livelock:recall-escape).  The return reads no
Recall itself above RECALL_MIN_DEPTH, and its wait for an active recall stood inside that
depth gate, so on 1F it walked on alternating (82667-82690, player.recalling) until the
loop detector stopped the bot, before the countdown ended.

Fix: the return waits for an active recall at every depth (fundraise:wait-recall, a
stationary reason the loop detector does not count).

Recorded: the boards are the incident capture's (tests/extract_n1a_525_stops_1115_fixtures.py:
the town-arrival checkpoint of the 12:46:14 visit replayed over the snapshot tail into the
dungeon, matching the record through decision 82622; ``policy.pkl.xz`` is that policy).
From decision 82623 the replay decides differently from the record (82623, 82630 and 82633
name another fundraising reason for the same keys, a state the checkpoint does not keep),
so every decision posts the recorded key and is compared only where the test says.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.latch_onset_capture import restore_checkpoint_bytes
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import RECALL_MIN_DEPTH, WAIT_KEY

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-525-stops-1115" / "yeek-recall"
RECALL_READ = 82666
CELLS = {(41, 22), (42, 23)}


class N1a525YeekRecall1115RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy_bytes = lzma.decompress((FIXTURE / "policy.pkl.xz").read_bytes())
        cls.boards = [json.loads(line) for line in lzma.decompress(
            (FIXTURE / "boards.jsonl.xz").read_bytes()).decode("utf-8").splitlines() if line]

    def replay(self):
        """(recorded decision, board, decided key, reason) for every logged decision."""
        policy = restore_checkpoint_bytes(HengbotPolicy, self.policy_bytes)
        self.addCleanup(lambda: policy._home_disposal.history_path.unlink(missing_ok=True))
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        ledger = Path(scratch.name) / "knowledge.jsonl"
        decided = []
        for entry in self.boards:
            recorded = entry["decision"]
            _consume_response_sequence(
                [json.dumps(record, ensure_ascii=False) + "\n" for record in entry["inputs"]],
                policy, lambda _key: True, policy._monrace_knowledge, parse_snapshots=False,
                knowledge_ledger_path=ledger)
            board = parse_snapshot(json.loads(json.dumps(entry["inputs"][-1])),
                                   policy._monrace_knowledge)
            key = policy.choose_key(board)
            decided.append((recorded, board, key, policy.last_reason))
            policy.confirm_key_posted(recorded["key"])
        return decided

    def test_the_recorded_walk_alternates_while_the_recall_counts_down(self):
        recalling = [entry["decision"] for entry in self.boards
                     if entry["decision"]["decision_sequence"] > RECALL_READ]
        read = next(entry["decision"] for entry in self.boards
                    if entry["decision"]["decision_sequence"] == RECALL_READ)
        self.assertEqual((read["key"], read["reason"]), ("rf", "livelock:recall-escape"))
        self.assertTrue(all(entry["inputs"][-1]["player"]["recalling"]
                            for entry in self.boards
                            if entry["decision"]["decision_sequence"] > RECALL_READ))
        self.assertEqual(
            {(row["position"]["y"], row["position"]["x"]) for row in recalling}, CELLS)
        self.assertGreaterEqual(
            sum(row["reason"] == "fundraise:seek-upstairs" for row in recalling), 20)
        self.assertLess(self.boards[0]["inputs"][-1]["floor"]["level"], RECALL_MIN_DEPTH)

    def test_the_return_waits_for_the_active_recall(self):
        decided = self.replay()
        after = [(recorded, key, reason) for recorded, board, key, reason in decided
                 if board.player.recalling]
        self.assertTrue(after)
        self.assertEqual(after[0][0]["decision_sequence"], RECALL_READ + 1)
        fundraising = [(key, reason) for _recorded, key, reason in after
                       if reason.startswith("fundraise:")]
        self.assertTrue(fundraising)
        self.assertEqual(set(fundraising), {(WAIT_KEY, "fundraise:wait-recall")})
        # Before the recall the return still walks to the stairs.
        before = [reason for recorded, board, _key, reason in decided
                  if not board.player.recalling
                  and recorded["decision_sequence"] > RECALL_READ - 6]
        self.assertIn("fundraise:seek-upstairs", before)


if __name__ == "__main__":
    unittest.main()
