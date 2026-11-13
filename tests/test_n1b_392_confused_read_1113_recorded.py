"""n1-b life-392 (2026-11-13 19:52, オークの洞窟19階, Lv20): Word of Recall read while confused.

Recorded (decision log): after the summoner shot ``fl4`` at turn 1124309 the
<スラーネッシュ>の女悪魔 (race 319: two CLAW CONFUSE blows, speed +10) confused the
player on every board.  The emergency ladder drank Cure Critical Wounds (``qc``,
cure-critical) and, below the low-HP line, Healing (``qd``, cure-status-healing)
until both ran out; each cure was undone before the next board.  From 1124490 the
low-HP walk gate replaced the ladder's step with ``rf`` (emergency:recall, slot f is
the Word of Recall): the game refused each read 「混乱していてできない！」
(cmd-read.cpp do_cmd_read_scroll: cmd_limit_confused, no game time), the executor
dropped the ``f`` continuation at the command barrier, and
emergency:await-consumable-confirmation waited (``5``).  Nineteen refused reads, a
loop stop, a restart, the same pair once more, and death at 19:52:34.

Fix: ``_can_read_scrolls`` is the game's whole read rule (blind, ``no_lite`` and
confused); the recall read (once_quest_recall.read_key) and every caller that left
the confusion test to itself now see the refusal before posting.

Source: tests/fixtures/n1b-392-confused-read-1113.json.gz
(tests/extract_n1b_392_confused_read_1113_fixture.py).  The policy starts on the
1124309 board; every decision goes through the public ``choose_key`` and a test says
when it edits a board (DECLARED CONSTRUCTED).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.model import parse_snapshot
from tests import test_me_staff_loops_1031_recorded as loops
from tests.support.recorded import QUAFF_PROMPT, READ_PROMPT, prompt_screen
from tests.test_me_nokey_1031_recorded import PostedKey


FIXTURE = Path(__file__).with_name("fixtures") / "n1b-392-confused-read-1113.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

FIRST, FIRST_READ, LAST = 1124309, 1124490, 1124513
CURES = range(1124323, 1124458 + 1)
CONFUSED_READ_BOARDS = (1124490, 1124503, 1124513)
REFUSAL = "混乱していてできない！"
RECALL_NAME, TELEPORT_NAME = "帰還の詔の巻物", "テレポートの巻物"


def replay(until, change=None):
    """The policy, the (edited) board and the key on ``until``."""
    policy = loops.new_policy(CASE, CASE["skill"], monraces=CASE["monraces"])
    for raw in CASE["boards"]:
        raw = copy.deepcopy(raw)
        if raw["turn"] == until and change is not None:
            change(raw)
        key = loops.decide(policy, raw)
        if raw["turn"] == until:
            return policy, raw, key
        if key:
            policy.confirm_key_posted(key)
    raise AssertionError(until)


def board(turn):
    return next(copy.deepcopy(raw) for raw in CASE["boards"] if raw["turn"] == turn)


def slot(raw, name):
    return next(item["slot"] for item in raw["inventory"] if name in item["name"])


class RecordedRowsTest(unittest.TestCase):
    def test_recorded_rows(self):
        rows = [(row["turn"], row["key"], row["reason"]) for row in CASE["decisions"]]
        raw = board(FIRST_READ)
        self.assertEqual(slot(raw, RECALL_NAME), "f")
        reads = [row for row in rows if row[1:] == ("rf", "emergency:recall")]
        self.assertEqual({row[0] for row in reads}, set(CONFUSED_READ_BOARDS))
        self.assertEqual(len(reads), 20)  # 19 before the loop stop, 1 after the restart
        self.assertIn((FIRST_READ, "5", "emergency:await-consumable-confirmation"), rows)
        for turn in CONFUSED_READ_BOARDS:
            self.assertTrue(board(turn)["player"]["status"]["confused"], turn)
        refused = [row for row in CASE["decisions"] if row["turn"] in CONFUSED_READ_BOARDS
                   and any(REFUSAL in message for message in row["messages"])]
        self.assertGreaterEqual(len(refused), 18)
        cures = {row[1:] for row in rows if row[0] in CURES}
        self.assertEqual(cures, {("qc", "emergency:cure-critical"),
                                 ("qd", "emergency:cure-status-healing")})


class ConfusedReadTest(PostedKey):
    def test_the_confused_boards_read_no_scroll(self):
        """Recorded: ``rf`` on each; now no read, and the key goes through the executor."""
        for turn in CONFUSED_READ_BOARDS:
            policy, raw, key = replay(turn)
            self.assertTrue(key, turn)
            self.assertFalse(key.startswith("r"), (turn, key, policy.last_reason))
            self.assertNotEqual(policy.last_reason, "emergency:recall", turn)
            snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            self.assertFalse(policy._can_read_scrolls(snapshot), turn)
            self.assertNotEqual(policy.last_reason,
                                "emergency:await-consumable-confirmation", turn)
            self.post(policy, raw, key)

    def test_control_unconfused_the_same_board_reads_teleportation(self):
        """DECLARED CONSTRUCTED: the 1124490 board without its confusion."""
        def clear(raw):
            raw["player"]["status"]["confused"] = False
        policy, raw, key = replay(FIRST_READ, clear)
        self.assertEqual((key, policy.last_reason),
                         ("r" + slot(raw, TELEPORT_NAME), "emergency:teleport"))
        self.post(policy, raw, key, screens=(prompt_screen(READ_PROMPT),))

    def test_the_cure_boards_replay_as_recorded(self):
        """The confusion cures are unchanged: the cheap cure above the low-HP line,
        Healing below it (owner 2026-11-01 「致命傷治癒はHP回復の効果に期待しない」)."""
        recorded = {row["turn"]: (row["key"], row["reason"]) for row in CASE["decisions"]}
        policy = loops.new_policy(CASE, CASE["skill"], monraces=CASE["monraces"])
        for raw in CASE["boards"]:
            if raw["turn"] > CURES[-1]:
                break
            raw = copy.deepcopy(raw)
            key = loops.decide(policy, raw)
            if raw["turn"] in CURES:
                self.assertEqual((key, policy.last_reason), recorded[raw["turn"]], raw["turn"])
                if raw["turn"] == CURES[0]:
                    self.post(policy, raw, key, screens=(prompt_screen(QUAFF_PROMPT),))
            policy.confirm_key_posted(key)


if __name__ == "__main__":
    unittest.main()
