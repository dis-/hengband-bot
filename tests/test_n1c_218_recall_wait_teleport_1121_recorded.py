"""While Recall counts down, an unseen attacker whose next hit kills is 即死 (n1-c life-218).

Owner 2026-11-15 (verbatim, LOCKED) 「即死か射線の通る T1 だけ・残り少なければ即死だけ」 (recall_wait_teleport):
during the Recall's countdown the self-teleport is read on the 即死 board.  Recorded (capture
n1c-218-20261121-death-48f): n1-c (Lv36, max HP 674) read Word of Recall on the Castle's 48F at
21:35:36; while it counted down an unseen monster breathed mana four times (about 250 each).  At
turn 3164643 (HP 132, the last breath 246, nobody in view) the board was 即死, yet the tiers'
unseen-loss correction counts only beside a visible hostile (threat_projection
``unseen_correction``), so recall_wait_teleport withheld the 13 Teleportation scrolls (deep_teleport
``no_means``), the unseen-attacker rung walked (unseen-recall:move) and the next breath killed it at
21:35:44.

Fixture tests/fixtures/n1c-218-recall-wait-teleport-1121: the town-arrival checkpoint of 21:35:03
(its journal, the visit that read the Recall to 48F) and the 106 state boards of 48F up to turn
3164643 with the keys and reasons the live process decided on them (``dungeon.json.xz``).  The town
rows and the dungeon boards are decided in order and the recorded keys delivered.

DECLARED CONSTRUCTED: the CLI's resume reads on, as in the live process.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.model import parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-218-recall-wait-teleport-1121"
FATAL_TURN = 3164643


class N1c218RecallWaitTeleportRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()

    def tearDown(self):
        self.scratch.cleanup()

    @staticmethod
    def deliver(policy, key):
        if key:
            policy.confirm_key_posted(key)
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def test_the_one_breath_kill_reads_teleportation_during_the_recall(self):
        policy, _journal, steps = load(FIXTURE, Path(self.scratch.name) / "fixture")
        self.addCleanup(policy._home_disposal.history_path.unlink, missing_ok=True)
        policy._me_power_resume_reads = True  # the live CLI's
        for recorded, supply in steps:
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                policy.choose_key(board)
            self.deliver(policy, recorded["key"])
        rows = json.loads(lzma.decompress((FIXTURE / "dungeon.json.xz").read_bytes()))
        decided = None
        for row in rows:
            board = parse_snapshot(row["board"], policy._monrace_knowledge)
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            if board.turn == FATAL_TURN:
                decided = (board, key, policy.last_reason)
                break
            self.deliver(policy, row["key"])
        board, key, reason = decided
        self.assertTrue(board.player.recalling)
        self.assertEqual((board.player.hp, board.dungeon_level), (132, 48))
        self.assertFalse(board.visible_monsters)
        self.assertEqual(rows[-1]["reason"], "unseen-recall:move")  # recorded
        self.assertEqual(reason, "emergency:teleport")
        self.assertTrue(key.startswith("r"), key)


if __name__ == "__main__":
    unittest.main()
