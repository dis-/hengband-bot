"""Quest 25 on n1-c life-200 (2026-11-12 12:03:00-12:03:13): the refused warning cell after a restart, recorded.

At 12:03:03 n1-c life-200 (Magic-Eater Lv36) stepped '8' from (6,29) toward (5,29) and the game
asked 「★ライト・クロスボウ『ウィザッパー』が鋭く震えた！ 本当にこのまま進むか？」.  The executor
refused it, and the next board, back at the command prompt, still carried the message.  The policy
latched (5,29) and its gate answered the ordinary ``warning:blocked-step`` wait, but a branch of
policy.choose_key (03e66aae72, 2026-09-19) turned that wait into no key on a board whose messages
held the prompt; the driver stopped (no-key-exhausted, 12:03:08).  The restarted process held no
latch, and the game asks again only for a forecast above 3/2 of the one it warned about
(warning.cpp process_warning ``warning_damage``), so the restart walked onto (5,29) unasked and
died there (12:03:13).  The same happened a minute earlier for (1,9)->(1,8): a Chaos breath took
HP 570 to 385.

Now the prompt-bearing board keeps its wait (rewritten by the policy's own no-wait rung), and the
refused cells are carried across the restart (warning_cell_record, the path cli.py gives it).

Recorded: tests/fixtures/n1c-200-q25-warning-restart-1112.json.gz
(tests/extract_n1c_200_q25_warning_restart_1112_fixture.py), one board per recorded decision of
the second process on the floor (decisions 0-54, from its restart to its no-key stop) and of the
third (0-8, from its restart to the death), with the recorded reason and key.  A fresh policy
decides the second process's boards in order through the public ``choose_key``; another fresh
policy, given the same record path, decides the third's first board.

DECLARED: decisions 0-3 of each process were the restart's periodic reads (skill experience and
the magic-eater lists, posted by the driver), which this harness does not issue, so those boards
are decided as the next one; the restarted processes hold no magic-eater lists (decisions 8-20 of
the second process aimed absorbed devices live, a launcher here).  Neither touches the warning.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot import warning_cell_record
from hengbot.model import Position, parse_snapshot
from tests.support import q25_house as q25

with gzip.open(Path(__file__).with_name("fixtures") / "n1c-200-q25-warning-restart-1112.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

PROMPT = "本当にこのまま進むか？[y/n]"
STOPPED = 54                      # the second process's prompt-bearing board (no key, live)
HERE, REFUSED = Position(6, 29), Position(5, 29)
QUEST_FLOOR = (0, 48, 25)
# Decided as recorded (declared above: 0-3 periodic reads, 8-20 magic-eater devices).
AS_RECORDED = (*range(4, 8), *range(21, STOPPED))


def new_policy(first, record):
    policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                quest_strategies=q25.STRATEGIES)
    policy._warning_cell_record_path = record
    policy._q25_battle_record_path = record.with_name("q25-battle.json")
    first = copy.deepcopy(first)
    policy.prime(parse_snapshot(first, policy._monrace_knowledge))
    policy.consume_skill_knowledge(dict(
        copy.deepcopy(CASE["skill"]), turn=first["turn"],
        player=dict(CASE["skill"]["player"], level=first["player"]["level"])))
    return policy


def decide(policy, raw):
    snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
    key = policy.choose_key(snapshot)
    if key is not None:
        policy.confirm_key_posted(key)
    return snapshot, key, policy.last_reason


def replay(*, carry=True):
    """The second process's answers by sequence, the third's first answer, and the record."""
    with TemporaryDirectory() as directory:
        record = Path(directory) / "warning-cells.json"
        boards = CASE["second"]["boards"]
        policy = new_policy(boards[0], record)
        second = {}
        for raw, row in zip(boards, CASE["second"]["recorded"]):
            snapshot, key, reason = decide(policy, raw)
            second[row["sequence"]] = (snapshot, key, reason, set(policy._warning_refused_cells))
        written = json.loads(record.read_text(encoding="utf-8"))
        if not carry:
            record.unlink()
        restarted = new_policy(CASE["third"]["boards"][0], record)
        third = decide(restarted, CASE["third"]["boards"][0])
        return second, (*third, set(restarted._warning_refused_cells)), written


ANSWERS = []


def answers():
    if not ANSWERS:
        ANSWERS.append(replay())
    return ANSWERS[0]


class N1c200WarningRestartRecordedTest(unittest.TestCase):

    def test_the_recording(self):
        second, third = CASE["second"], CASE["third"]
        last, before = second["boards"][STOPPED], second["boards"][STOPPED - 1]
        self.assertEqual((last["floor"]["quest_id"], last["floor"]["level"]), (25, 48))
        self.assertIn(PROMPT, last["messages"])
        self.assertEqual((before["player"]["y"], before["player"]["x"]), (HERE.y, HERE.x))
        self.assertEqual((second["recorded"][STOPPED - 1]["key"], second["recorded"][STOPPED - 1]["reason"]),
                         ("8", "quest25:walk"))
        self.assertEqual((second["recorded"][STOPPED]["key"], second["recorded"][STOPPED]["reason"]),
                         (None, "warning:blocked-step"))
        # The restarted process walked the refused step again, unasked.
        walked = third["recorded"][4]
        self.assertEqual((walked["key"], walked["reason"]), ("8", "quest25:walk"))
        self.assertEqual(third["boards"][4]["turn"], last["turn"])
        landed = third["boards"][5]
        self.assertEqual((landed["player"]["y"], landed["player"]["x"]), (REFUSED.y, REFUSED.x))
        self.assertFalse(any(PROMPT in message for board in third["boards"][:6]
                             for message in board["messages"]))

    def test_the_second_process_decides_as_recorded(self):
        second, _third, _written = answers()
        recorded = {row["sequence"]: (row["key"], row["reason"]) for row in CASE["second"]["recorded"]}
        self.assertEqual({seq: second[seq][1:3] for seq in AS_RECORDED},
                         {seq: recorded[seq] for seq in AS_RECORDED})

    def test_the_prompt_bearing_board_keeps_a_key(self):
        second, _third, _written = answers()
        snapshot, key, reason, refused = second[STOPPED]
        self.assertEqual(snapshot.player.position, HERE)
        self.assertIsNotNone(key, reason)          # live: None -> no-key-exhausted stop
        self.assertNotEqual(key[:1], "8")          # never the refused step
        self.assertIn(REFUSED, refused)

    def test_the_refused_cell_is_recorded_for_the_floor(self):
        _second, _third, written = answers()
        self.assertEqual(tuple(written["floor"]), QUEST_FLOOR)
        self.assertEqual(written["turn"], CASE["second"]["boards"][STOPPED]["turn"])
        self.assertIn([REFUSED.y, REFUSED.x], written["state"]["refused"])

    def test_the_restart_still_avoids_the_refused_cell(self):
        _second, (snapshot, key, reason, refused), _written = answers()
        self.assertEqual(snapshot.player.position, HERE)
        self.assertIn(REFUSED, refused)
        self.assertIsNotNone(key, reason)
        self.assertNotEqual(key[:1], "8", reason)  # live: '8' quest25:walk onto (5,29), the death

    def test_control_without_the_record_the_restart_walks_onto_it(self):
        _second, (_snapshot, key, reason, refused), _written = replay(carry=False)
        self.assertNotIn(REFUSED, refused)
        self.assertEqual((key, reason), ("8", "quest25:walk"))


class _Snap:
    def __init__(self, floor_key, turn, in_town=False):
        self.floor_key, self.turn, self.in_town = floor_key, turn, in_town


class WarningCellRecordTest(unittest.TestCase):
    """The restore is bound to the same floor at the same or a later turn, once per process."""

    def _written(self, directory):
        policy = ConservativePolicy()
        policy._warning_cell_record_path = Path(directory) / "warning-cells.json"
        policy._warning_refused_cells.add(REFUSED)
        policy._trap_warning_cells[Position(1, 9)] = 2
        warning_cell_record.record(policy, _Snap(QUEST_FLOOR, 100))
        return policy._warning_cell_record_path

    def _restored(self, path, snapshot):
        policy = ConservativePolicy()
        policy._warning_cell_record_path = path
        warning_cell_record.restore(policy, snapshot)
        return policy

    def test_same_floor_later_turn_restores_both(self):
        with TemporaryDirectory() as directory:
            policy = self._restored(self._written(directory), _Snap(QUEST_FLOOR, 100))
            self.assertEqual(policy._warning_refused_cells, {REFUSED})
            self.assertIn(REFUSED, policy._engagement_avoid_cells)
            self.assertEqual(policy._trap_warning_cells, {Position(1, 9): 2})

    def test_other_floor_earlier_turn_or_town_restores_nothing(self):
        with TemporaryDirectory() as directory:
            path = self._written(directory)
            for snapshot in (_Snap((0, 47, 25), 100), _Snap(QUEST_FLOOR, 99),
                             _Snap(QUEST_FLOOR, 100, in_town=True)):
                policy = self._restored(path, snapshot)
                self.assertFalse(policy._warning_refused_cells)
                self.assertFalse(policy._trap_warning_cells)

    def test_read_once_per_process(self):
        with TemporaryDirectory() as directory:
            path = self._written(directory)
            policy = self._restored(path, _Snap((0, 47, 25), 100))
            warning_cell_record.restore(policy, _Snap(QUEST_FLOOR, 100))
            self.assertFalse(policy._warning_refused_cells)

    def test_unchanged_cells_are_not_rewritten(self):
        with TemporaryDirectory() as directory:
            path = self._written(directory)
            policy = ConservativePolicy()
            policy._warning_cell_record_path = path
            policy._warning_refused_cells.add(REFUSED)
            policy._trap_warning_cells[Position(1, 9)] = 2
            warning_cell_record.record(policy, _Snap(QUEST_FLOOR, 200))
            path.unlink()
            warning_cell_record.record(policy, _Snap(QUEST_FLOOR, 300))
            self.assertFalse(path.exists())
            warning_cell_record.record(policy, _Snap((0, 47, 25), 300))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["floor"], [0, 47, 25])


if __name__ == "__main__":
    unittest.main()
